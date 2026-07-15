#!/usr/bin/env python3
"""
生成每艘船每天的Speed Loss数据（符合DynamoDB格式）
使用ISO 19030标准方法定义baseline
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
OUTPUT_PATH = r"C:\Users\KIRALI~1\AppData\Local\Temp\daily_speedloss.csv"

REF_WATER_TEMP = 15
REF_DRAFT = 8.0
BASELINE_START_DAYS = 7    # DD后第7天开始
BASELINE_END_DAYS = 14     # DD后第14天结束


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

    # 基础过滤
    vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
    vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
    vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]

    # 计算原始STW
    vt_df['stw_raw'] = pd.to_numeric(vt_df['SPEED_THROUGH_WATER'], errors='coerce')

    # 计算修正后的STW
    print("Calculating ISO 19030 corrections...")
    vt_df['stw_corrected'] = vt_df.apply(calculate_corrected_stw, axis=1)

    # 清理数据
    vt_df = vt_df[['vessel', 'day', 'stw_raw', 'stw_corrected']].dropna()
    vt_df = vt_df[(vt_df['stw_raw'] > 0) & (vt_df['stw_corrected'] > 0)]
    vt_df = vt_df.sort_values(['vessel', 'day']).reset_index(drop=True)

    print(f"Loaded {len(vt_df)} valid records\n")

    # 为每艘船确定baseline
    baselines = {}

    for vessel in sorted(vt_df['vessel'].unique()):
        vessel_df = vt_df[vt_df['vessel'] == vessel]
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        # 找最早的DD事件
        dd_events = sorted([
            float(m['event_day'])
            for _, m in vessel_maint.iterrows()
            if m['event_type'] == 'DD'
        ])

        if len(dd_events) > 0:
            earliest_dd = dd_events[0]
            baseline_window = vessel_df[
                (vessel_df['day'] > earliest_dd + BASELINE_START_DAYS) &
                (vessel_df['day'] <= earliest_dd + BASELINE_END_DAYS)
            ]

            if len(baseline_window) >= 3:
                baseline_stw = baseline_window['stw_corrected'].mean()
                baselines[vessel] = baseline_stw
                print(f"{vessel}: baseline STW = {baseline_stw:.2f} knots (from DD day {earliest_dd:.0f}, {len(baseline_window)} records)")
            else:
                print(f"{vessel}: insufficient baseline data for DD at day {earliest_dd:.0f}")
        else:
            print(f"{vessel}: no DD event found, using overall mean as baseline")
            baselines[vessel] = vessel_df['stw_corrected'].mean()

    print(f"\nBaselines established: {len(baselines)} vessels\n")

    # 生成每日speed loss数据
    results = []

    for vessel in sorted(vt_df['vessel'].unique()):
        if vessel not in baselines:
            continue

        print(f"Processing {vessel}...")
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day')
        baseline_stw = baselines[vessel]

        for _, row in vessel_df.iterrows():
            day = row['day']
            stw_raw = row['stw_raw']
            stw_corrected = row['stw_corrected']

            # 计算speed loss
            speed_loss = (stw_corrected - baseline_stw) / baseline_stw * 100

            results.append({
                'ship': vessel,
                'day': round(day, 1),
                'stw_raw': round(stw_raw, 2),
                'stw_corrected': round(stw_corrected, 2),
                'baseline_stw': round(baseline_stw, 2),
                'speed_loss_pct': round(speed_loss, 2),
            })

    output_df = pd.DataFrame(results)
    output_df = output_df.sort_values(['ship', 'day']).reset_index(drop=True)

    output_df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8')
    print(f"\nSaved to {OUTPUT_PATH}")

    # 统计
    print("\n" + "=" * 80)
    print("DAILY SPEED LOSS STATISTICS")
    print("=" * 80)

    print(f"\nTotal records: {len(output_df)}")
    print(f"Date range: day {output_df['day'].min():.0f} to {output_df['day'].max():.0f}")

    print("\nSpeed Loss distribution:")
    print(f"  Mean: {output_df['speed_loss_pct'].mean():+.2f}%")
    print(f"  Median: {output_df['speed_loss_pct'].median():+.2f}%")
    print(f"  Min: {output_df['speed_loss_pct'].min():+.2f}%")
    print(f"  Max: {output_df['speed_loss_pct'].max():+.2f}%")
    print(f"  Std Dev: {output_df['speed_loss_pct'].std():.2f}%")

    print("\nBy ship:")
    for vessel in sorted(output_df['ship'].unique()):
        ship_data = output_df[output_df['ship'] == vessel]
        print(f"  {vessel:4s}: {len(ship_data):4d} records, speed_loss: {ship_data['speed_loss_pct'].mean():+6.2f}% "
              f"(range: {ship_data['speed_loss_pct'].min():+6.2f}% to {ship_data['speed_loss_pct'].max():+6.2f}%)")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
