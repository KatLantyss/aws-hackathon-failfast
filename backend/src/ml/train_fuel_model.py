"""
油耗預測模型訓練腳本
使用 LightGBM 訓練油耗預測模型
"""
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import joblib
import sys
import os

# 添加父目錄到路徑
sys.path.append(os.path.dirname(os.path.dirname(__file__)))


class FuelConsumptionModelTrainer:
    """油耗預測模型訓練器"""
    
    def __init__(self, data_path: str = "../hackathon-data"):
        self.data_path = data_path
        self.model = None
        self.feature_columns = []
        
    def load_data(self):
        """載入訓練數據"""
        print("📊 載入數據...")
        vt_df = pd.read_csv(f"{self.data_path}/vt_fd.csv")
        maintenance_df = pd.read_csv(f"{self.data_path}/maintenance.csv")
        
        print(f"✓ 載入 {len(vt_df)} 筆航行日報")
        print(f"✓ 載入 {len(maintenance_df)} 筆維護事件")
        
        return vt_df, maintenance_df
    
    def feature_engineering(self, df: pd.DataFrame, maintenance_df: pd.DataFrame):
        """特徵工程"""
        print("\n🔧 特徵工程...")
        
        df = df.copy()
        
        # 1. 基礎特徵
        self.feature_columns = [
            'AVG_SPEED',
            'ME_AVG_RPM',
            'DISPLACEMENT',
            'WIND_SCALE',
            'SEA_HEIGHT',
            'FORE_DRAFT',
            'AFTER_DRAFT',
            'MID_DRAFT',
            'CARGO_ON_BOARD',
            'SEA_WATER_TEMP',
            'HOURS_FULL_SPEED',
        ]
        
        # 2. 時間退化特徵（距上次維護天數）
        for vessel_id in df['De-identification Name'].unique():
            vessel_mask = df['De-identification Name'] == vessel_id
            vessel_maintenance = maintenance_df[maintenance_df['ship_id'] == vessel_id]
            
            # 距上次 DD（乾塢）天數
            df.loc[vessel_mask, 'days_since_dd'] = self._calculate_days_since_event(
                df[vessel_mask], vessel_maintenance, 'DD'
            )
            
            # 距上次 UWC（船殼清洗）天數
            df.loc[vessel_mask, 'days_since_uwc'] = self._calculate_days_since_event(
                df[vessel_mask], vessel_maintenance, 'UWC'
            )
            
            # 距上次 PP（螺旋槳拋光）天數
            df.loc[vessel_mask, 'days_since_pp'] = self._calculate_days_since_event(
                df[vessel_mask], vessel_maintenance, 'PP'
            )
        
        self.feature_columns.extend(['days_since_dd', 'days_since_uwc', 'days_since_pp'])
        
        # 3. 船型特徵
        df['vessel_type'] = df['De-identification Name'].apply(
            lambda x: 1 if x in ['S1','S2','S3','S4','S5','S6','S7','S8','S21'] else 2
        )
        self.feature_columns.append('vessel_type')
        
        print(f"✓ 建立 {len(self.feature_columns)} 個特徵")
        return df
    
    def _calculate_days_since_event(self, vessel_df, maintenance_df, event_type):
        """計算距離特定維護事件的天數"""
        events = maintenance_df[
            maintenance_df['event_type'].str.contains(event_type, na=False)
        ]['event_day'].values
        
        days_since = []
        for day in vessel_df['NOON_UTC']:
            previous_events = events[events < day]
            if len(previous_events) > 0:
                days_since.append(day - previous_events[-1])
            else:
                days_since.append(day)  # 從開始算起
        
        return days_since
    
    def prepare_training_data(self, df: pd.DataFrame):
        """準備訓練數據"""
        print("\n📦 準備訓練數據...")
        
        # 篩選訓練船（S1-S12）
        train_df = df[df['De-identification Name'].str.startswith('S1')].copy()
        
        # 篩選穩態日（全速≥22hr、風速≤4）
        train_df = train_df[
            (train_df['HOURS_FULL_SPEED'] >= 22) &
            (train_df['WIND_SCALE'] <= 4)
        ]
        
        print(f"✓ 篩選出 {len(train_df)} 筆穩態訓練樣本")
        
        # 準備目標變數（所有燃料類型的油耗）
        fuel_columns = [
            'ME_FULLSPEED_CONSUMP_HSHFO',
            'ME_FULLSPEED_CONSUMP_ULSFO',
            'ME_FULLSPEED_CONSUMP_VLSFO',
            'ME_FULLSPEED_CONSUMP_LSMGO',
            'ME_FULLSPEED_CONSUMP_BIO_HSFO'
        ]
        
        # 合併所有燃料的數據（每日僅使用單一燃料）
        train_data = []
        for _, row in train_df.iterrows():
            for fuel_col in fuel_columns:
                if pd.notna(row[fuel_col]) and row[fuel_col] != 'HIDDEN' and row[fuel_col] != 'PREDICT':
                    try:
                        fuel_value = float(row[fuel_col])
                        if fuel_value > 0:
                            record = row[self.feature_columns].to_dict()
                            record['fuel_consumption'] = fuel_value
                            record['fuel_type'] = fuel_col
                            train_data.append(record)
                    except (ValueError, TypeError):
                        continue
        
        train_df_final = pd.DataFrame(train_data)
        
        # 移除缺失值
        train_df_final = train_df_final.dropna()
        
        print(f"✓ 最終訓練數據: {len(train_df_final)} 筆")
        
        # 分割特徵和目標
        X = train_df_final[self.feature_columns]
        y = train_df_final['fuel_consumption']
        
        return train_test_split(X, y, test_size=0.2, random_state=42)
    
    def train_model(self, X_train, y_train, X_test, y_test):
        """訓練 LightGBM 模型"""
        print("\n🚀 訓練 LightGBM 模型...")
        
        # LightGBM 參數
        params = {
            'objective': 'regression',
            'metric': 'rmse',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.9,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': -1
        }
        
        # 建立數據集
        train_data = lgb.Dataset(X_train, label=y_train)
        test_data = lgb.Dataset(X_test, label=y_test, reference=train_data)
        
        # 訓練
        self.model = lgb.train(
            params,
            train_data,
            num_boost_round=1000,
            valid_sets=[test_data],
            callbacks=[
                lgb.early_stopping(stopping_rounds=50),
                lgb.log_evaluation(period=100)
            ]
        )
        
        print("✓ 模型訓練完成")
        
        return self.model
    
    def evaluate_model(self, X_test, y_test):
        """評估模型"""
        print("\n📈 模型評估...")
        
        y_pred = self.model.predict(X_test, num_iteration=self.model.best_iteration)
        
        mse = mean_squared_error(y_test, y_pred)
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100
        
        print(f"  RMSE:  {rmse:.3f} MT/day")
        print(f"  MAE:   {mae:.3f} MT/day")
        print(f"  R²:    {r2:.4f}")
        print(f"  MAPE:  {mape:.2f}%")
        
        return {
            'rmse': rmse,
            'mae': mae,
            'r2': r2,
            'mape': mape
        }
    
    def save_model(self, output_path: str = "models/fuel_model.pkl"):
        """儲存模型"""
        print(f"\n💾 儲存模型至 {output_path}...")
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        model_package = {
            'model': self.model,
            'feature_columns': self.feature_columns,
            'version': '1.0.0'
        }
        
        joblib.dump(model_package, output_path)
        print("✓ 模型已儲存")
    
    def run(self):
        """執行完整訓練流程"""
        print("=" * 60)
        print("🚢 船舶油耗預測模型訓練")
        print("=" * 60)
        
        # 1. 載入數據
        vt_df, maintenance_df = self.load_data()
        
        # 2. 特徵工程
        vt_df = self.feature_engineering(vt_df, maintenance_df)
        
        # 3. 準備訓練數據
        X_train, X_test, y_train, y_test = self.prepare_training_data(vt_df)
        
        # 4. 訓練模型
        self.train_model(X_train, y_train, X_test, y_test)
        
        # 5. 評估模型
        metrics = self.evaluate_model(X_test, y_test)
        
        # 6. 儲存模型
        self.save_model()
        
        print("\n" + "=" * 60)
        print("✅ 訓練完成！")
        print("=" * 60)
        
        return metrics


if __name__ == "__main__":
    trainer = FuelConsumptionModelTrainer()
    metrics = trainer.run()
