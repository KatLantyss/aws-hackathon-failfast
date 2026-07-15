"""
Speed Loss 計算與可視化管道
根據 ISO 19030 框架，分層計算並可視化船舶推進效能損失
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings('ignore')

class SpeedLossPipeline:
    """Speed Loss 完整計算管道"""

    # 燃料熱值對照表 (MJ/kg)
    FUEL_LCV = {
        'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
        'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
        'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
        'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
        'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4
    }

    def __init__(self, vt_fd_path, maintenance_path):
        """
        初始化管道

        Args:
            vt_fd_path: 正午報表 CSV 路徑
            maintenance_path: 維修事件 CSV 路徑
        """
        print("[INFO] Loading data...")
        self.vt_fd = pd.read_csv(vt_fd_path)
        self.maintenance = pd.read_csv(maintenance_path)

        # 重命名以便後續處理
        self.vt_fd.rename(columns={'De-identification Name': 'ship_id'}, inplace=True)
        self.maintenance.rename(columns={'event_day': 'NOON_UTC'}, inplace=True)

        print(f"[OK] Loaded {len(self.vt_fd)} noon report records")
        print(f"[OK] Loaded {len(self.maintenance)} maintenance event records")

    def step_1_data_cleaning(self):
        """步驟 1：數據清洗與聚合"""
        print("\n[STEP 1] Data Cleaning & Aggregation")

        df = self.vt_fd.copy()

        # 移除純錨泊/靠港日 (全速航行時數 = 0)
        df = df[df['HOURS_FULL_SPEED'] > 0].copy()
        print(f"[OK] After removing anchor days: {len(df)} records")

        # 移除關鍵欄位缺失的行
        key_cols = ['SPEED_THROUGH_WATER', 'HOURS_FULL_SPEED', 'WIND_SCALE']
        df = df.dropna(subset=key_cols)
        print(f"[OK] 清洗缺失值後：{len(df)} 條記錄")

        # 轉換數據類型
        numeric_cols = ['SPEED_THROUGH_WATER', 'HOURS_FULL_SPEED', 'WIND_SCALE',
                       'AVG_SPEED', 'DISPLACEMENT', 'CARGO_ON_BOARD', 'NOON_UTC']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        self.vt_fd_clean = df
        return df

    def step_2_daily_foc(self):
        """
        步驟 2：計算 Daily FOC（每日油耗）

        Daily FOC = 該日統一燃料標準的全速油耗 (MT/day)
        處理多燃料情況：用熱值折算為 VLSFO 當量
        異常值過濾：移除 FOC < 10 MT/day 的記錄（數據異常）
        """
        print("\n[STEP] 步驟 2：計算 Daily FOC")

        df = self.vt_fd_clean.copy()

        # 定義燃料欄位
        fuel_cols = ['ME_FULLSPEED_CONSUMP_HSHFO', 'ME_FULLSPEED_CONSUMP_ULSFO',
                    'ME_FULLSPEED_CONSUMP_VLSFO', 'ME_FULLSPEED_CONSUMP_LSMGO',
                    'ME_FULLSPEED_CONSUMP_BIO_HSFO']

        # 確定當日使用的燃料類型
        def get_primary_fuel(row):
            """識別當日主要使用的燃料"""
            fuels = []
            for fuel in fuel_cols:
                try:
                    val = pd.to_numeric(row[fuel], errors='coerce')
                    if pd.notna(val) and val > 0:
                        fuels.append((fuel, val))
                except:
                    pass

            if not fuels:
                return None, None

            # 返回使用量最多的燃料
            primary = max(fuels, key=lambda x: x[1])
            return primary

        # 計算每行的 Daily FOC
        foc_data = []
        for idx, row in df.iterrows():
            fuel_info = get_primary_fuel(row)

            if fuel_info[0] is None:
                foc_data.append({
                    'fuel_type': 'UNKNOWN',
                    'daily_foc': np.nan,
                    'daily_foc_vlsfo_equiv': np.nan
                })
            else:
                fuel_col, consump = fuel_info
                foc_data.append({
                    'fuel_type': fuel_col,
                    'daily_foc': consump,
                    'daily_foc_vlsfo_equiv': self._convert_to_vlsfo(fuel_col, consump)
                })

        df = pd.concat([df, pd.DataFrame(foc_data)], axis=1)

        # 移除異常低的 FOC 值（< 10 MT/day 通常是數據異常）
        initial_count = len(df[df['daily_foc'].notna()])
        df = df[(df['daily_foc'].isna()) | (df['daily_foc'] >= 10)].copy()
        final_count = len(df[df['daily_foc'].notna()])
        removed_count = initial_count - final_count

        print(f"[OK] 計算完成：{final_count} 條有效 FOC 記錄（移除 {removed_count} 條異常值）")

        # 統計燃料使用情況
        print("\n燃料使用統計：")
        for fuel in fuel_cols:
            count = len(df[df['fuel_type'] == fuel])
            if count > 0:
                print(f"  - {fuel}: {count} 天")

        self.vt_fd_with_foc = df
        return df

    def _convert_to_vlsfo(self, fuel_type, consumption_mt):
        """
        將任意燃料折算為 VLSFO 當量
        基於熱值換算
        """
        if pd.isna(consumption_mt):
            return np.nan

        lcv_fuel = self.FUEL_LCV.get(fuel_type, 40.2)
        lcv_vlsfo = self.FUEL_LCV['ME_FULLSPEED_CONSUMP_VLSFO']

        # 能量守恆：consumption_mt * lcv_fuel = equiv_vlsfo * lcv_vlsfo
        equiv_vlsfo = consumption_mt * lcv_fuel / lcv_vlsfo

        return equiv_vlsfo

    def step_3_speed_loss_layered(self, window_days=7):
        """
        步驟 3：分層計算 Speed Loss

        層級 1：相對基準法（使用同船歷史最佳性能）
        層級 2：多因素回歸法（預期 FOC 模型）
        層級 3：維修前後對比法

        Args:
            window_days: 滾動窗口大小（天）
        """
        print("\n[STEP] 步驟 3：分層計算 Speed Loss")

        df = self.vt_fd_with_foc.copy()

        # 移除 ship_id 為 NaN 的行
        df = df[df['ship_id'].notna()].copy()

        # 按船舶分組
        speed_loss_data = []

        for ship_id in df['ship_id'].unique():
            ship_df = df[df['ship_id'] == ship_id].sort_values('NOON_UTC').reset_index(drop=True)

            if len(ship_df) == 0:
                continue

            print(f"\n  Processing ship {ship_id}...")

            # 層級 1：相對基準法
            ship_df['foc_rolling_avg'] = ship_df['daily_foc_vlsfo_equiv'].rolling(
                window=window_days, center=True, min_periods=1
            ).mean()

            # 計算該船的基準 FOC（歷史最佳 = 最低消耗，排除異常）
            valid_foc = ship_df['daily_foc_vlsfo_equiv'].dropna()

            if len(valid_foc) > 10:
                # 使用 10% 分位（最佳的 10% 航次）作為基準
                baseline_foc = valid_foc.quantile(0.10)
            elif len(valid_foc) > 0:
                baseline_foc = valid_foc.min()
            else:
                baseline_foc = 50

            # 確保基準值合理（通常在 30-100 MT/day）
            baseline_foc = max(baseline_foc, 30)

            ship_df['speed_loss_pct_l1'] = ((ship_df['daily_foc_vlsfo_equiv'] - baseline_foc) / baseline_foc * 100).clip(lower=0)

            # 層級 2：多因素特徵工程
            ship_df = self._add_degradation_features(ship_df)

            # 計算預期 FOC（簡化模型：基於風力、負載、季節性）
            ship_df['expected_foc'] = self._calculate_expected_foc(ship_df, baseline_foc)

            ship_df['speed_loss_pct_l2'] = ((ship_df['expected_foc'] - ship_df['daily_foc_vlsfo_equiv']) /
                                           ship_df['expected_foc'] * 100).clip(lower=0)

            speed_loss_data.append(ship_df)

        df_with_speed_loss = pd.concat(speed_loss_data, ignore_index=True)

        # 層級 3：維修效益（事後處理）
        df_with_speed_loss = self._compute_maintenance_impact(df_with_speed_loss)

        print(f"\n[OK] Speed Loss 計算完成")

        self.vt_fd_with_speed_loss = df_with_speed_loss
        return df_with_speed_loss

    def _add_degradation_features(self, ship_df):
        """添加設備衰退特徵"""

        if len(ship_df) == 0:
            return ship_df

        # 距離上次維修的天數（如果有維修記錄）
        ship_id = ship_df['ship_id'].iloc[0]
        if pd.isna(ship_id):
            return ship_df

        maintenance_events = self.maintenance[self.maintenance['ship_id'] == ship_id]

        if len(maintenance_events) > 0:
            # 找到 UWI 或 DD 事件
            significant_events = maintenance_events[
                maintenance_events['event_type'].isin(['UWI', 'DD', 'UWI+PP', 'UWC+PP'])
            ].sort_values('NOON_UTC')

            if len(significant_events) > 0:
                last_event_day = significant_events['NOON_UTC'].iloc[-1]
                ship_df['days_since_maintenance'] = ship_df['NOON_UTC'] - last_event_day
            else:
                ship_df['days_since_maintenance'] = ship_df['NOON_UTC']
        else:
            ship_df['days_since_maintenance'] = ship_df['NOON_UTC']

        # 季節性（簡化：使用相對天數的週期）
        ship_df['season_sin'] = np.sin(2 * np.pi * ship_df['NOON_UTC'] / 365)
        ship_df['season_cos'] = np.cos(2 * np.pi * ship_df['NOON_UTC'] / 365)

        # 風力影響
        ship_df['wind_impact'] = (ship_df['WIND_SCALE'] / 4.0) ** 1.5  # 風力影響非線性

        return ship_df

    def _calculate_expected_foc(self, ship_df, baseline_foc):
        """
        計算預期 FOC（簡化的多因素模型）

        預期 FOC = baseline_foc × (1 + 設備衰退因子 + 風力因子 + 季節性因子)
        """

        # 設備衰退模型：天數越久，衰退越多（按 sqrt 衰減）
        degradation_factor = np.sqrt(ship_df['days_since_maintenance'].fillna(0) / 365.0) * 0.15

        # 風力影響（風力越強，所需油耗越多）
        wind_factor = ship_df['wind_impact'].fillna(0) * 0.1

        # 季節性因子（簡化：冬季需要更多動力）
        season_factor = (ship_df['season_sin'].fillna(0) * 0.05).clip(-0.05, 0.05)

        # 負載因子（如果有貨物數據）
        if 'CARGO_ON_BOARD' in ship_df.columns:
            # 負載越高，相對效率越好（邊際成本降低）
            max_cargo = ship_df['CARGO_ON_BOARD'].max()
            if max_cargo > 0:
                load_factor = -(ship_df['CARGO_ON_BOARD'].fillna(0) / max_cargo) * 0.05
            else:
                load_factor = 0
        else:
            load_factor = 0

        expected_foc = baseline_foc * (1 + degradation_factor + wind_factor + season_factor + load_factor)

        return expected_foc.clip(lower=baseline_foc)

    def _compute_maintenance_impact(self, df):
        """計算維修前後的效能改善"""

        maintenance_events = self.maintenance.copy()

        for idx, event in maintenance_events.iterrows():
            ship_id = event['ship_id']
            event_day = event['NOON_UTC']
            event_type = event['event_type']

            # 篩選該船舶的數據
            ship_mask = df['ship_id'] == ship_id

            # 維修後 30 天的改善幅度
            after_mask = (df['ship_id'] == ship_id) & (df['NOON_UTC'] > event_day) & (df['NOON_UTC'] <= event_day + 30)
            before_mask = (df['ship_id'] == ship_id) & (df['NOON_UTC'] <= event_day) & (df['NOON_UTC'] > event_day - 30)

            if len(df[before_mask]) > 0 and len(df[after_mask]) > 0:
                foc_before = df[before_mask]['daily_foc_vlsfo_equiv'].mean()
                foc_after = df[after_mask]['daily_foc_vlsfo_equiv'].mean()

                improvement_pct = ((foc_before - foc_after) / foc_before * 100) if foc_before > 0 else 0

                df.loc[after_mask, 'maintenance_event'] = event_type
                df.loc[after_mask, 'maintenance_improvement_pct'] = improvement_pct

        return df

    def step_4_integrate_maintenance(self):
        """步驟 4：整合維修事件標籤"""
        print("\n[STEP] 步驟 4：整合維修事件標籤")

        df = self.vt_fd_with_speed_loss.copy()

        # 為每條記錄添加最近維修事件的信息
        for idx, row in df.iterrows():
            ship_id = row['ship_id']
            day = row['NOON_UTC']

            # 找到此前最近的維修事件
            ship_maint = self.maintenance[self.maintenance['ship_id'] == ship_id]
            recent_maint = ship_maint[ship_maint['NOON_UTC'] <= day].sort_values('NOON_UTC', ascending=False)

            if len(recent_maint) > 0:
                last_event = recent_maint.iloc[0]
                df.loc[idx, 'last_maintenance_type'] = last_event['event_type']
                df.loc[idx, 'last_maintenance_day'] = last_event['NOON_UTC']
                df.loc[idx, 'days_since_last_maintenance'] = day - last_event['NOON_UTC']
            else:
                df.loc[idx, 'days_since_last_maintenance'] = day

        print(f"[OK] 維修事件整合完成")
        self.vt_fd_final = df
        return df

    def step_5_generate_timeseries(self):
        """步驟 5：生成時間序列與統計指標"""
        print("\n[STEP] 步驟 5：生成時間序列與統計指標")

        df = self.vt_fd_final.copy()

        # 按船舶和日期分組的統計
        timeseries_stats = []

        for ship_id in df['ship_id'].unique():
            ship_data = df[df['ship_id'] == ship_id].sort_values('NOON_UTC')

            stats = {
                'ship_id': ship_id,
                'days_count': len(ship_data),
                'avg_foc': ship_data['daily_foc_vlsfo_equiv'].mean(),
                'min_foc': ship_data['daily_foc_vlsfo_equiv'].min(),
                'max_foc': ship_data['daily_foc_vlsfo_equiv'].max(),
                'foc_std': ship_data['daily_foc_vlsfo_equiv'].std(),
                'avg_speed_loss_l1': ship_data['speed_loss_pct_l1'].mean(),
                'avg_speed_loss_l2': ship_data['speed_loss_pct_l2'].mean(),
                'avg_wind_scale': ship_data['WIND_SCALE'].mean(),
                'avg_speed_through_water': ship_data['SPEED_THROUGH_WATER'].mean(),
            }
            timeseries_stats.append(stats)

        stats_df = pd.DataFrame(timeseries_stats)

        print("\n船隊效能統計：")
        print(stats_df.to_string(index=False))

        self.timeseries_stats = stats_df
        return stats_df

    def step_6_detect_anomalies(self, threshold_pct=20):
        """
        步驟 6：異常檢測與告警規則

        Args:
            threshold_pct: Speed Loss 異常閾值（%）
        """
        print(f"\n[WARNING] 步驟 6：異常檢測（閾值：{threshold_pct}%）")

        df = self.vt_fd_final.copy()

        anomalies = []

        for ship_id in df['ship_id'].unique():
            ship_data = df[df['ship_id'] == ship_id]

            # 規則 1：Speed Loss 異常高
            high_loss = ship_data[ship_data['speed_loss_pct_l1'] > threshold_pct]
            for idx, row in high_loss.iterrows():
                anomalies.append({
                    'ship_id': ship_id,
                    'day': row['NOON_UTC'],
                    'type': 'HIGH_SPEED_LOSS',
                    'severity': 'HIGH' if row['speed_loss_pct_l1'] > threshold_pct * 1.5 else 'MEDIUM',
                    'value': row['speed_loss_pct_l1'],
                    'threshold': threshold_pct
                })

            # 規則 2：FOC 異常高（超過過去 30 天平均值 2 倍標差）
            rolling_mean = ship_data['daily_foc_vlsfo_equiv'].rolling(window=30).mean()
            rolling_std = ship_data['daily_foc_vlsfo_equiv'].rolling(window=30).std()
            high_foc = ship_data[(ship_data['daily_foc_vlsfo_equiv'] > rolling_mean + 2 * rolling_std)]

            for idx, row in high_foc.iterrows():
                anomalies.append({
                    'ship_id': ship_id,
                    'day': row['NOON_UTC'],
                    'type': 'ABNORMAL_FOC',
                    'severity': 'MEDIUM',
                    'value': row['daily_foc_vlsfo_equiv'],
                    'mean': rolling_mean.loc[idx],
                    'std': rolling_std.loc[idx]
                })

        anomalies_df = pd.DataFrame(anomalies)

        print(f"\n檢測到 {len(anomalies_df)} 個異常事件：")
        if len(anomalies_df) > 0:
            print(anomalies_df.groupby('type')['ship_id'].count())

        self.anomalies = anomalies_df
        return anomalies_df

    def export_results(self, output_dir='./speed_loss_output'):
        """匯出計算結果"""
        import os
        os.makedirs(output_dir, exist_ok=True)

        print(f"\n[STEP] 匯出結果到 {output_dir}")

        # 匯出完整結果集
        self.vt_fd_final.to_csv(f'{output_dir}/speed_loss_complete.csv', index=False)
        print(f"[OK] 完整數據：speed_loss_complete.csv")

        # 匯出統計指標
        self.timeseries_stats.to_csv(f'{output_dir}/fleet_statistics.csv', index=False)
        print(f"[OK] 船隊統計：fleet_statistics.csv")

        # 匯出異常事件
        if len(self.anomalies) > 0:
            self.anomalies.to_csv(f'{output_dir}/anomalies.csv', index=False)
            print(f"[OK] 異常告警：anomalies.csv")

        # 匯出可視化數據（JSON 格式，便於前端使用）
        viz_data = self._prepare_viz_data()
        # 清理所有 NaN 值
        viz_data_clean = self._clean_nan_values(viz_data)
        with open(f'{output_dir}/visualization_data.json', 'w', encoding='utf-8') as f:
            json.dump(viz_data_clean, f, indent=2)
        print(f"[OK] 可視化數據：visualization_data.json")

    def _clean_nan_values(self, obj):
        """遞歸清理所有 NaN 和 Inf 值"""
        if isinstance(obj, dict):
            return {k: self._clean_nan_values(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._clean_nan_values(v) for v in obj]
        elif isinstance(obj, float):
            if pd.isna(obj) or np.isinf(obj):
                return None
            return obj
        return obj

    def _prepare_viz_data(self):
        """準備用於可視化的數據結構"""

        df = self.vt_fd_final.copy()

        viz_data = {
            'fleet_summary': {
                'total_ships': len(df['ship_id'].unique()),
                'total_days': len(df),
                'avg_fleet_speed_loss': df['speed_loss_pct_l1'].mean(),
                'worst_ship': df.groupby('ship_id')['speed_loss_pct_l1'].mean().idxmax(),
                'best_ship': df.groupby('ship_id')['speed_loss_pct_l1'].mean().idxmin(),
            },
            'timeseries': {},
            'maintenance_events': []
        }

        # 為每艘船添加時間序列
        for ship_id in df['ship_id'].unique():
            ship_data = df[df['ship_id'] == ship_id].sort_values('NOON_UTC')

            viz_data['timeseries'][ship_id] = {
                'days': ship_data['NOON_UTC'].tolist(),
                'speed_loss_l1': ship_data['speed_loss_pct_l1'].fillna(0).tolist(),
                'speed_loss_l2': ship_data['speed_loss_pct_l2'].fillna(0).tolist(),
                'daily_foc': ship_data['daily_foc_vlsfo_equiv'].fillna(0).tolist(),
                'wind_scale': ship_data['WIND_SCALE'].fillna(0).tolist(),
                'speed_through_water': ship_data['SPEED_THROUGH_WATER'].fillna(0).tolist(),
            }

        # 維修事件
        for idx, event in self.maintenance.iterrows():
            viz_data['maintenance_events'].append({
                'ship_id': event['ship_id'],
                'day': event['NOON_UTC'],
                'event_type': event['event_type'],
                'propeller_condition': event.get('propeller_condition', ''),
                'hull_fouling_type': event.get('hull_fouling_type', ''),
            })

        return viz_data

    def run_full_pipeline(self):
        """執行完整管道"""
        print("=" * 60)
        print("[INFO] 陽明海運 - Speed Loss 分析管道")
        print("=" * 60)

        self.step_1_data_cleaning()
        self.step_2_daily_foc()
        self.step_3_speed_loss_layered()
        self.step_4_integrate_maintenance()
        self.step_5_generate_timeseries()
        self.step_6_detect_anomalies()
        self.export_results()

        print("\n" + "=" * 60)
        print("[DONE] 管道執行完成！")
        print("=" * 60)

        return self.vt_fd_final


if __name__ == '__main__':
    # 初始化管道
    pipeline = SpeedLossPipeline(
        vt_fd_path='vt_fd.csv',
        maintenance_path='maintenance.csv'
    )

    # 執行完整流程
    results = pipeline.run_full_pipeline()

    # 顯示样本結果
    print("\n[STEP] 樣本結果（前 10 行）：")
    print(results[['ship_id', 'NOON_UTC', 'daily_foc_vlsfo_equiv',
                   'speed_loss_pct_l1', 'speed_loss_pct_l2', 'WIND_SCALE']].head(10))
