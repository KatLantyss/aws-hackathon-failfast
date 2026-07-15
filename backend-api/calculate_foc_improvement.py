#!/usr/bin/env python3
"""
直接计算维修效益：对比前后30天的平均FOC
改善 = (FOC_前30天 - FOC_后30天) / FOC_前30天 * 100
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
OUTPUT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\maintenance_foc_improvement.csv"

WINDOW_DAYS = 30
MIN_DATA_POINTS = 3


def calc_daily_foc(row):
    """题目公式：Daily FOC = ME_FULLSPEED_CONSUMP_VLSFO / HOURS_FULL_SPEED × 24"""
    hfs = float(row.get('HOURS_FULL_SPEED', 0))
    if hfs < 22:
        return None

    try:
        vlsfo = float(row.get('ME_FULLSPEED_CONSUMP_VLSFO', 0))
    except:
        vlsfo = 0

    if vlsfo <= 0:
        return None

    # 直接按题目公式计算
    daily_foc = vlsfo / hfs * 24.0
    return daily_foc


def main():
    print("Loading data...")
    maint_df = pd.read_csv(MAINT_PATH)
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)

    # 准备数据
    vt_df.rename(columns={
        'De-identification Name': 'vessel',
        'NOON_UTC': 'day',
    }, inplace=True)

    vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
    vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
    vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]

    vt_df['foc'] = vt_df.apply(calc_daily_foc, axis=1)
    vt_df = vt_df[['vessel', 'day', 'foc']].dropna()
    vt_df = vt_df[vt_df['foc'] > 0]

    print(f"Loaded {len(vt_df)} valid FOC records\n")

    # 计算每个维修事件的改善
    results = []

    for vessel in sorted(vt_df['vessel'].unique()):
        print(f"{vessel}:")
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day')
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        for _, maint in vessel_maint.iterrows():
            event_day = float(maint['event_day'])
            event_type = maint['event_type']

            # 前30天
            before_w = vessel_df[
                (vessel_df['day'] >= event_day - WINDOW_DAYS) &
                (vessel_df['day'] < event_day)
            ]

            # 后30天
            after_w = vessel_df[
                (vessel_df['day'] > event_day) &
                (vessel_df['day'] <= event_day + WINDOW_DAYS)
            ]

            # 只有数据点足够时才计算
            if len(before_w) >= MIN_DATA_POINTS and len(after_w) >= MIN_DATA_POINTS:
                foc_before = before_w['foc'].mean()
                foc_after = after_w['foc'].mean()
                improvement = (foc_before - foc_after) / foc_before * 100

                results.append({
                    'ship': vessel,
                    'event_day': event_day,
                    'event_type': event_type,
                    'foc_before_30d': round(foc_before, 2),
                    'foc_after_30d': round(foc_after, 2),
                    'foc_improvement_pct': round(improvement, 2),
                    'n_before': len(before_w),
                    'n_after': len(after_w),
                })

                indicator = "✓" if improvement > 0 else "✗"
                print(f"  Day {event_day:6.0f} {event_type:8s}: "
                      f"before={foc_before:6.2f}, after={foc_after:6.2f}, "
                      f"improvement={improvement:6.2f}% {indicator}")

    # 输出 CSV
    output_df = pd.DataFrame(results)
    output_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}")

    # 验证结果
    print("\n" + "=" * 80)
    print("VALIDATION")
    print("=" * 80)

    valid_df = output_df[output_df['foc_improvement_pct'].notna()]
    improved = (valid_df['foc_improvement_pct'] > 0).sum()
    total = len(valid_df)
    improvement_rate = improved / total * 100 if total > 0 else 0

    print(f"Total maintenance events: {total}")
    print(f"Events with improvement (>0%): {improved} ({improvement_rate:.1f}%)")
    print(f"Average improvement: {valid_df['foc_improvement_pct'].mean():.2f}%\n")

    print("By maintenance type:")
    for mtype in ['DD', 'UWC+PP', 'UWC', 'PP', 'UWI+PP', 'UWI']:
        group = valid_df[valid_df['event_type'] == mtype]
        if len(group) == 0:
            continue

        improved_type = (group['foc_improvement_pct'] > 0).sum()
        total_type = len(group)
        avg_improvement = group['foc_improvement_pct'].mean()
        rate = improved_type / total_type * 100 if total_type > 0 else 0

        print(f"  {mtype:8s}: {improved_type:2d}/{total_type:2d} ({rate:5.1f}%) avg_improvement={avg_improvement:6.2f}%")

    print("\n" + "=" * 80)
    print("Expected hierarchy:")
    print("  DD        should have highest improvement (>50%)")
    print("  UWC+PP    should have high improvement (>40%)")
    print("  UWC       should have medium improvement (>20%)")
    print("  PP        should have modest improvement (>10%)")
    print("  UWI+PP    should have small improvement (>5%)")
    print("  UWI       should have minimal improvement (~0%, just inspection)")
    print("=" * 80)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
