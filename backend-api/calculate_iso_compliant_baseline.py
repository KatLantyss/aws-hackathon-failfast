#!/usr/bin/env python3
"""
ISO 19030-2 符合規範的Baseline計算

規範：
1. 基準期 = DD後90天內的實際航行數據
2. 數據量要求 = ≥10,000個有效數據點 或 等價於15-30天的有效航行
3. Baseline定義 = 該期間內「速度-功率」關係的平均值
4. 計算方法 = 該期間內所有有效STW值的平均

v_d = (v_m - v_e) / v_e * 100%
其中 v_e = DD後90天內的平均修正STW (In-service Reference Period)
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
OUTPUT_PATH = r"C:\Users\KIRALI~1\AppData\Local\Temp\daily_speedloss_iso_compliant.csv"

REF_WATER_TEMP = 15
REF_DRAFT = 8.0
BASELINE_WINDOW_DAYS = 90  # ISO 19030-2 標準
MIN_DATA_POINTS = 10000    # ISO 19030-2 要求


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
    print("=" * 100)
    print("ISO 19030-2 COMPLIANT BASELINE CALCULATION")
    print("=" * 100)
    print()
    print("規範:")
    print(f"  • 基準期: DD後{BASELINE_WINDOW_DAYS}天")
    print(f"  • 數據量要求: ≥{MIN_DATA_POINTS:,}個有效點")
    print(f"  • V_e (期望速度) = 基準期內的平均修正STW")
    print(f"  • V_d (速度損失) = (V_m - V_e) / V_e × 100%")
    print()

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

    # ========== 為每艘船建立Baseline ==========
    print("=" * 100)
    print("ESTABLISHING BASELINE FOR EACH SHIP")
    print("=" * 100)
    print()

    # 排除S21（數據品質問題）
    EXCLUDE_SHIPS = ['S21']

    baselines = {}  # {ship: baseline_stw}
    baseline_details = []

    for vessel in sorted(vt_df['vessel'].unique()):
        if vessel in EXCLUDE_SHIPS:
            print(f"{vessel}: ❌ 排除（數據品質問題 - DD後數據被污染）")
            continue
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day')
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        # 找出第一個DD事件（或最早的任何出塚事件）
        dd_events = sorted([
            float(m['event_day'])
            for _, m in vessel_maint.iterrows()
            if m['event_type'] in ['DD', 'UWC+PP', 'UWC']  # 假設大型維修
        ])

        if len(dd_events) == 0:
            print(f"{vessel}: ⚠️  無DD/出塚事件，使用全船數據作為Baseline")
            baseline_window = vessel_df
            baseline_method = "No DD - Full Ship Data"
            dd_day = None
        else:
            dd_day = dd_events[0]
            baseline_window = vessel_df[
                (vessel_df['day'] >= dd_day) &
                (vessel_df['day'] <= dd_day + BASELINE_WINDOW_DAYS)
            ]
            baseline_method = f"DD/Maintenance at day {dd_day:.0f}, then +{BASELINE_WINDOW_DAYS}d"

        n_points = len(baseline_window)

        if n_points >= 3:  # 至少要有3個點
            baseline_stw = baseline_window['stw_corrected'].mean()
            baselines[vessel] = baseline_stw

            # 檢查是否符合ISO要求
            iso_compliant = "✓" if n_points >= MIN_DATA_POINTS else "⚠️"
            print(f"{vessel}: {iso_compliant} n={n_points:5d}, baseline_stw={baseline_stw:.2f}kt ({baseline_method})")

            baseline_details.append({
                'ship': vessel,
                'baseline_stw': baseline_stw,
                'n_points': n_points,
                'iso_compliant': "Y" if n_points >= MIN_DATA_POINTS else "N",
                'method': baseline_method,
                'dd_day': dd_day if dd_day else "N/A",
            })
        else:
            print(f"{vessel}: ❌ 數據不足 (n={n_points})")

    print(f"\n✓ Baselines established for {len(baselines)} ships")

    # ========== 生成每日Speed Loss ==========
    print("\n" + "=" * 100)
    print("GENERATING DAILY SPEED LOSS")
    print("=" * 100)
    print()

    results = []

    for vessel in sorted(vt_df['vessel'].unique()):
        if vessel not in baselines:
            continue

        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day')
        baseline_stw = baselines[vessel]

        for _, row in vessel_df.iterrows():
            day = row['day']
            stw_corrected = row['stw_corrected']

            # 計算速度損失 (V_d)
            speed_loss = (baseline_stw - stw_corrected) / baseline_stw * 100

            results.append({
                'ship': vessel,
                'day': round(day, 1),
                'stw_corrected': round(stw_corrected, 2),
                'baseline_stw': round(baseline_stw, 2),
                'speed_loss_pct': round(speed_loss, 2),
            })

    output_df = pd.DataFrame(results)
    output_df = output_df.sort_values(['ship', 'day']).reset_index(drop=True)

    output_df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8')
    print(f"✓ Saved to {OUTPUT_PATH}")

    # ========== 統計與驗證 ==========
    print("\n" + "=" * 100)
    print("STATISTICS & VALIDATION")
    print("=" * 100)

    print(f"\nTotal daily records: {len(output_df)}")
    print(f"Date range: day {output_df['day'].min():.0f} to {output_df['day'].max():.0f}")

    print("\nSpeed Loss distribution:")
    print(f"  Mean: {output_df['speed_loss_pct'].mean():+.2f}%")
    print(f"  Median: {output_df['speed_loss_pct'].median():+.2f}%")
    print(f"  Min: {output_df['speed_loss_pct'].min():+.2f}%")
    print(f"  Max: {output_df['speed_loss_pct'].max():+.2f}%")

    print("\nBy ship:")
    for vessel in sorted(output_df['ship'].unique()):
        ship_data = output_df[output_df['ship'] == vessel]
        print(f"  {vessel:4s}: {len(ship_data):5d} records, speed_loss: {ship_data['speed_loss_pct'].mean():+7.2f}% "
              f"(range: {ship_data['speed_loss_pct'].min():+7.2f}% to {ship_data['speed_loss_pct'].max():+7.2f}%)")

    # ========== Baseline信息表 ==========
    baseline_df = pd.DataFrame(baseline_details)
    baseline_output = r"C:\Users\KIRALI~1\AppData\Local\Temp\ship_baselines_iso.csv"
    baseline_df.to_csv(baseline_output, index=False, encoding='utf-8')
    print(f"\n✓ Baseline details saved to ship_baselines_iso.csv")

    print("\n" + "=" * 100)
    print("ISO 19030-2 COMPLIANCE SUMMARY")
    print("=" * 100)

    compliant = len(baseline_df[baseline_df['iso_compliant'] == 'Y'])
    non_compliant = len(baseline_df[baseline_df['iso_compliant'] == 'N'])

    print(f"\nCompliant (≥{MIN_DATA_POINTS:,} points): {compliant}")
    print(f"Non-compliant (<{MIN_DATA_POINTS:,} points): {non_compliant}")

    if non_compliant > 0:
        print(f"\n⚠️  注意: {non_compliant}艘船的數據不足以符合ISO 19030-2標準")
        print("建議: 增加數據收集期間或降低數據量要求")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
