#!/usr/bin/env python3
"""
用新的 RPM 正规化参数（±10 RPM, 1+ 数据点）
重新计算 speed_loss_maintenance_impact.csv 中的 rpm_normalized_foc_drop_pct 列
"""
import pandas as pd
import sys

# RPM 参数（新的放宽版本）
RPM_TOLERANCE = 10
MIN_POINTS = 1
WINDOW_DAYS = 30

# 文件路径
VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
OUTPUT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\speed_loss_maintenance_impact.csv"


def calc_rpm_normalized(timeline_df, event_day):
    """计算 RPM 正规化 FOC 改善 %。返回百分比和数据点数"""
    before = timeline_df[(timeline_df['day'] >= event_day - WINDOW_DAYS) &
                         (timeline_df['day'] < event_day)]
    after = timeline_df[(timeline_df['day'] > event_day) &
                        (timeline_df['day'] <= event_day + WINDOW_DAYS)]

    if len(before) < 3 or len(after) < 3:
        return None, 0, 0

    try:
        rpm_after_avg = after['rpm'].mean()

        before_in_range = before[abs(before['rpm'] - rpm_after_avg) <= RPM_TOLERANCE]
        after_in_range = after[abs(after['rpm'] - rpm_after_avg) <= RPM_TOLERANCE]

        if len(before_in_range) < MIN_POINTS or len(after_in_range) < MIN_POINTS:
            return None, len(before_in_range), len(after_in_range)

        foc_before = before_in_range['foc'].mean()
        foc_after = after_in_range['foc'].mean()

        if foc_before <= 0 or foc_after <= 0:
            return None, len(before_in_range), len(after_in_range)

        improvement = ((foc_before - foc_after) / foc_before) * 100
        return round(improvement, 2), len(before_in_range), len(after_in_range)
    except:
        return None, 0, 0


def main():
    print("=" * 70)
    print("Calculating RPM-normalized FOC improvement")
    print(f"RPM params: ±{RPM_TOLERANCE} RPM, {MIN_POINTS}+ points per side")
    print("=" * 70)

    # 读取数据
    print("\nLoading vt_fd.csv...")
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)
    vt_df.rename(columns={'De-identification Name': 'vessel', 'NOON_UTC': 'day',
                          'ME_AVG_RPM': 'rpm', 'ME_FULLSPEED_CONSUMP_VLSFO': 'foc'},
                 inplace=True)
    vt_df = vt_df[['vessel', 'day', 'rpm', 'foc']].dropna()
    print(f"Loaded {len(vt_df)} records")

    print("Loading maintenance.csv...")
    maint_df = pd.read_csv(MAINT_PATH)
    print(f"Loaded {len(maint_df)} events")

    print("Loading output CSV...")
    output_df = pd.read_csv(OUTPUT_PATH)
    print(f"Loaded {len(output_df)} rows")

    # 计算
    print("\nCalculating...")
    improvements = []
    n_before_list = []
    n_after_list = []
    success_count = 0

    for idx, row in output_df.iterrows():
        vessel = row['ship']
        day = float(row['event_day'])

        vessel_timeline = vt_df[vt_df['vessel'] == vessel].copy()

        if len(vessel_timeline) == 0:
            improvements.append(None)
            n_before_list.append(0)
            n_after_list.append(0)
            continue

        improvement, n_before, n_after = calc_rpm_normalized(vessel_timeline, day)
        improvements.append(improvement)
        n_before_list.append(n_before)
        n_after_list.append(n_after)

        if improvement is not None:
            success_count += 1
            print(f"  {vessel:3s} Day {day:6.0f}: {improvement:6.2f}% (before={n_before}, after={n_after})")

    # 更新列
    output_df['rpm_normalized_foc_drop_pct'] = improvements
    output_df['n_before'] = n_before_list
    output_df['n_after'] = n_after_list

    # 保存
    output_df.to_csv(OUTPUT_PATH, index=False)
    print("\n" + "=" * 70)
    print(f"✅ Completed!")
    print(f"   Total events: {len(output_df)}")
    print(f"   Events with RPM-normalized improvement: {success_count}")
    print(f"   Coverage: {100*success_count/len(output_df):.1f}%")
    print(f"   Output: {OUTPUT_PATH}")
    print("=" * 70)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
