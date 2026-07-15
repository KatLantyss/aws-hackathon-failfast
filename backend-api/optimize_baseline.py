#!/usr/bin/env python3
"""
優化baseline定義 - 找最適合的方法

ISO 19030標準：
baseline (V_e) = 船在最乾淨狀態的速度
通常是DD後7-14天的平均STW

問題分析：
1. 有些船沒有DD事件 → 怎麼定baseline?
2. 有些船DD事件太少，7-14天沒有足夠數據 → 用什麼備選?
3. Baseline應該是固定的還是動態的?
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"

REF_WATER_TEMP = 15
REF_DRAFT = 8.0


def wind_resistance_correction(stw, wind_speed, wind_direction):
    try:
        if pd.isna(wind_speed) or wind_speed <= 0:
            return 0
        return wind_speed * 0.1
    except:
        return 0


def water_temp_correction(stw, water_temp_actual, ref_temp=REF_WATER_TEMP):
    try:
        if pd.isna(water_temp_actual):
            return 0
        temp_diff = water_temp_actual - ref_temp
        return -temp_diff * 0.02
    except:
        return 0


def seawater_density_correction(stw, water_temp, cargo_weight=None):
    try:
        if pd.isna(water_temp):
            return 0
        temp_diff = water_temp - REF_WATER_TEMP
        return -temp_diff * 0.01
    except:
        return 0


def draft_correction(stw, fore_draft, after_draft, ref_draft=REF_DRAFT):
    try:
        if pd.isna(fore_draft) or pd.isna(after_draft):
            return 0
        avg_draft = (float(fore_draft) + float(after_draft)) / 2
        if avg_draft <= 0:
            return 0
        draft_diff = avg_draft - ref_draft
        return -draft_diff * 0.15
    except:
        return 0


def wave_height_correction(stw, sea_height):
    try:
        if pd.isna(sea_height) or sea_height == 0:
            return 0
        return -float(sea_height) * 0.05
    except:
        return 0


def calculate_corrected_stw(row):
    try:
        stw_raw = float(row.get('SPEED_THROUGH_WATER', 0))
        if stw_raw <= 0:
            return None

        wind_speed = float(row.get('WIND_SPEED', 0)) if pd.notna(row.get('WIND_SPEED')) else 0
        wind_dir = float(row.get('WIND_DIRECTION', 0)) if pd.notna(row.get('WIND_DIRECTION')) else 0
        water_temp = float(row.get('SEA_WATER_TEMP', 0)) if pd.notna(row.get('SEA_WATER_TEMP')) else REF_WATER_TEMP
        fore_draft = float(row.get('FORE_DRAFT', 0)) if pd.notna(row.get('FORE_DRAFT')) else REF_DRAFT
        after_draft = float(row.get('AFTER_DRAFT', 0)) if pd.notna(row.get('AFTER_DRAFT')) else REF_DRAFT
        sea_height = float(row.get('SEA_HEIGHT', 0)) if pd.notna(row.get('SEA_HEIGHT')) else 0

        wind_corr = wind_resistance_correction(stw_raw, wind_speed, wind_dir)
        temp_corr = water_temp_correction(stw_raw, water_temp)
        density_corr = seawater_density_correction(stw_raw, water_temp)
        draft_corr = draft_correction(stw_raw, fore_draft, after_draft)
        wave_corr = wave_height_correction(stw_raw, sea_height)

        stw_corrected = stw_raw + wind_corr + temp_corr + density_corr + draft_corr + wave_corr
        return stw_corrected
    except:
        return None


def main():
    print("Loading data...")
    maint_df = pd.read_csv(MAINT_PATH)
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)

    vt_df.rename(columns={
        'De-identification Name': 'vessel',
        'NOON_UTC': 'day',
    }, inplace=True)

    # 基礎過濾
    vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
    vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
    vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]

    vt_df['stw_raw'] = pd.to_numeric(vt_df['SPEED_THROUGH_WATER'], errors='coerce')
    vt_df['stw_corrected'] = vt_df.apply(calculate_corrected_stw, axis=1)

    vt_df = vt_df[['vessel', 'day', 'stw_raw', 'stw_corrected']].dropna()
    vt_df = vt_df[(vt_df['stw_raw'] > 0) & (vt_df['stw_corrected'] > 0)]
    vt_df = vt_df.sort_values(['vessel', 'day']).reset_index(drop=True)

    print(f"Loaded {len(vt_df)} valid records\n")

    # ========== BASELINE 定義分析 ==========
    print("=" * 100)
    print("BASELINE DEFINITION ANALYSIS")
    print("=" * 100)

    baseline_results = []

    for vessel in sorted(vt_df['vessel'].unique()):
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day')
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        # 方法1: DD後7-14天 (ISO標準)
        dd_events = sorted([
            float(m['event_day'])
            for _, m in vessel_maint.iterrows()
            if m['event_type'] == 'DD'
        ])

        baseline_dd = None
        dd_baseline_day = None
        if len(dd_events) > 0:
            earliest_dd = dd_events[0]
            baseline_window = vessel_df[
                (vessel_df['day'] > earliest_dd + 7) &
                (vessel_df['day'] <= earliest_dd + 14)
            ]
            if len(baseline_window) >= 3:
                baseline_dd = baseline_window['stw_corrected'].mean()
                dd_baseline_day = earliest_dd

        # 方法2: 95分位數 (代表最好狀況)
        baseline_p95 = vessel_df['stw_corrected'].quantile(0.95)

        # 方法3: 歷史最高速度
        baseline_max = vessel_df['stw_corrected'].max()

        # 方法4: 全船平均
        baseline_mean = vessel_df['stw_corrected'].mean()

        # 決定最終baseline
        if baseline_dd is not None:
            final_baseline = baseline_dd
            method = "DD後7-14天 (最佳)"
        else:
            # 沒有DD的船，用95分位
            final_baseline = baseline_p95
            method = "95分位數 (無DD備選)"

        # 計算當前污染程度
        latest_date = vessel_df['day'].max()
        latest_stw = vessel_df[vessel_df['day'] == latest_date]['stw_corrected'].mean()
        current_pollution = (final_baseline - latest_stw) / final_baseline * 100

        baseline_results.append({
            'ship': vessel,
            'baseline_method': method,
            'baseline_stw': final_baseline,
            'dd_baseline': baseline_dd,
            'p95': baseline_p95,
            'max': baseline_max,
            'mean': baseline_mean,
            'latest_stw': latest_stw,
            'current_pollution_pct': current_pollution,
            'has_dd': 'Y' if baseline_dd is not None else 'N',
            'dd_day': dd_baseline_day if dd_baseline_day else 'N/A',
        })

    baseline_df = pd.DataFrame(baseline_results)

    print("\n【Baseline Recommendation for Each Ship】\n")
    print(f"{'Ship':<6} {'Method':<30} {'Baseline STW':<15} {'Pollution%':<12} {'Latest STW':<12}")
    print("-" * 100)

    for _, row in baseline_df.iterrows():
        print(f"{row['ship']:<6} {row['baseline_method']:<30} {row['baseline_stw']:>10.2f}kt "
              f"{row['current_pollution_pct']:>10.2f}%  {row['latest_stw']:>10.2f}kt")

    print("\n" + "=" * 100)
    print("DETAILED COMPARISON FOR EACH METHOD")
    print("=" * 100)

    for _, row in baseline_df.iterrows():
        print(f"\n【{row['ship']}】")
        if row['has_dd'] == 'Y':
            print(f"  ✓ 有DD事件 (Day {row['dd_day']:.0f})")
            print(f"    - DD後7-14天平均 (推薦): {row['dd_baseline']:.2f} knots")
        else:
            print(f"  ✗ 無DD事件")

        print(f"    - 95分位數:               {row['p95']:.2f} knots")
        print(f"    - 全部最高速度:           {row['max']:.2f} knots")
        print(f"    - 全船平均:               {row['mean']:.2f} knots")
        print(f"\n  選定: {row['baseline_method']}")
        print(f"  Baseline STW: {row['baseline_stw']:.2f} knots")
        print(f"  當前污染程度: {row['current_pollution_pct']:+.2f}% (相比baseline)")

    print("\n" + "=" * 100)
    print("RECOMMENDATION")
    print("=" * 100)

    has_dd = (baseline_df['has_dd'] == 'Y').sum()
    no_dd = (baseline_df['has_dd'] == 'N').sum()

    print(f"\n統計:")
    print(f"  有DD事件的船: {has_dd}")
    print(f"  無DD事件的船: {no_dd}")

    print(f"\n推薦方案：")
    print(f"""
1. ✓ 【最優】每艘船用各自的baseline:
   - 有DD的船: 用DD後7-14天的平均 (符合ISO 19030)
   - 無DD的船: 用95分位數作為備選

2. ✓ 【次優】全船統一baseline:
   - 所有船都用95分位數
   - 優點: 簡單統一
   - 缺點: 無法反映船的真實污染程度

3. ✗ 【不推薦】用全船平均:
   - 代表平均污染狀態，不是最乾淨狀態
   - 無法用於衡量污染程度

結論: 推薦方案1 (分船定義baseline)
    """)

    # 輸出baseline表
    output_path = r"C:\Users\KIRALI~1\AppData\Local\Temp\ship_baselines.csv"
    baseline_df.to_csv(output_path, index=False, encoding='utf-8')
    print(f"\n✓ Baseline定義表已保存: ship_baselines.csv")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
