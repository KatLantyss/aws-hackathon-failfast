#!/usr/bin/env python3
"""
测试不同的时间窗口大小（15、20、30、45、60天）
看哪个窗口大小给出最合理的结果
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"

# 参考值
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
        cargo = float(row.get('CARGO_ON_BOARD', 0)) if pd.notna(row.get('CARGO_ON_BOARD')) else 0

        wind_corr = wind_resistance_correction(stw_raw, wind_speed, wind_dir)
        temp_corr = water_temp_correction(stw_raw, water_temp)
        density_corr = seawater_density_correction(stw_raw, water_temp, cargo)
        draft_corr = draft_correction(stw_raw, fore_draft, after_draft)
        wave_corr = wave_height_correction(stw_raw, sea_height)

        stw_corrected = stw_raw + wind_corr + temp_corr + density_corr + draft_corr + wave_corr
        return stw_corrected
    except:
        return None


def analyze_window(window_days):
    """分析给定时间窗口的结果"""
    maint_df = pd.read_csv(MAINT_PATH)
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)

    vt_df.rename(columns={
        'De-identification Name': 'vessel',
        'NOON_UTC': 'day',
    }, inplace=True)

    vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
    vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
    vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]

    vt_df['stw_raw'] = pd.to_numeric(vt_df['SPEED_THROUGH_WATER'], errors='coerce')
    vt_df['stw_corrected'] = vt_df.apply(calculate_corrected_stw, axis=1)

    vt_df = vt_df[['vessel', 'day', 'stw_raw', 'stw_corrected']].dropna()
    vt_df = vt_df[(vt_df['stw_raw'] > 0) & (vt_df['stw_corrected'] > 0)]
    vt_df = vt_df.sort_values(['vessel', 'day']).reset_index(drop=True)

    # 计算维修效果
    results = []

    for vessel in sorted(vt_df['vessel'].unique()):
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day')
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        for _, maint in vessel_maint.iterrows():
            event_day = float(maint['event_day'])
            event_type = maint['event_type']

            before_w = vessel_df[
                (vessel_df['day'] >= event_day - window_days) &
                (vessel_df['day'] < event_day)
            ]
            after_w = vessel_df[
                (vessel_df['day'] > event_day) &
                (vessel_df['day'] <= event_day + window_days)
            ]

            if len(before_w) >= 3 and len(after_w) >= 3:
                stw_before = before_w['stw_corrected'].mean()
                stw_after = after_w['stw_corrected'].mean()
                improvement = (stw_after - stw_before) / stw_before * 100

                results.append({
                    'event_type': event_type,
                    'improvement': improvement,
                    'improved': improvement > 0,
                    'n_before': len(before_w),
                    'n_after': len(after_w),
                })

    result_df = pd.DataFrame(results)

    if len(result_df) > 0:
        improved = result_df['improved'].sum()
        total = len(result_df)
        improvement_rate = improved / total * 100
        avg_improvement = result_df['improvement'].mean()

        return {
            'window': window_days,
            'total': total,
            'improved': improved,
            'improvement_rate': improvement_rate,
            'avg_improvement': avg_improvement,
            'by_type': result_df.groupby('event_type').agg({
                'improved': 'sum',
                'improvement': ['count', 'mean']
            })
        }

    return None


def main():
    print("=" * 80)
    print("Testing different time window sizes")
    print("=" * 80)
    print()

    windows = [15, 20, 30, 45, 60, 75, 90]
    results_all = {}

    for window in windows:
        print(f"Analyzing {window}-day window...")
        result = analyze_window(window)
        if result:
            results_all[window] = result

    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)
    print()

    print(f"{'Window':<10} {'Total':<8} {'Improved':<12} {'Rate':<10} {'Avg %':<10}")
    print("-" * 80)

    for window in windows:
        if window in results_all:
            r = results_all[window]
            print(f"{window:>3} days   {r['total']:<8} {r['improved']:<12} {r['improvement_rate']:>6.1f}%    {r['avg_improvement']:>6.2f}%")

    print("\n" + "=" * 80)
    print("DETAILED BREAKDOWN BY TYPE (30 vs 15 vs 60 days)")
    print("=" * 80)

    for window in [15, 30, 60, 90]:
        if window in results_all:
            print(f"\n{window}-day window:")
            r = results_all[window]
            for mtype in ['DD', 'UWC+PP', 'UWC', 'PP', 'UWI+PP', 'UWI']:
                type_data = r['by_type'].loc[mtype] if mtype in r['by_type'].index else None
                if type_data is not None:
                    improved = int(type_data[('improved', 'sum')])
                    total = int(type_data[('improvement', 'count')])
                    avg = type_data[('improvement', 'mean')]
                    rate = improved / total * 100 if total > 0 else 0
                    print(f"  {mtype:8s}: {improved:2d}/{total:2d} ({rate:5.1f}%) avg={avg:6.2f}%")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
