#!/usr/bin/env python3
"""
检查原始 STW 数据
看某些维修事件前后的 STW 变化
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"

# 准备数据
print("Loading data...")
maint_df = pd.read_csv(MAINT_PATH)
vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)

vt_df.rename(columns={
    'De-identification Name': 'vessel',
    'NOON_UTC': 'day',
    'SPEED_THROUGH_WATER': 'stw',
}, inplace=True)

# 过滤：风力 <= 4, HOURS >= 22
vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]

vt_df['stw'] = pd.to_numeric(vt_df['stw'], errors='coerce')
vt_df = vt_df[['vessel', 'day', 'stw']].dropna()
vt_df = vt_df[(vt_df['stw'] > 0)].sort_values(['vessel', 'day']).reset_index(drop=True)

print(f"Loaded {len(vt_df)} valid STW records\n")

# 检查几个关键事件
test_cases = [
    ('S1', 1560, 'PP', 'Propeller Polishing'),
    ('S11', 570, 'UWC+PP', 'Hull Cleaning + Polishing'),
    ('S11', 1132, 'UWC', 'Hull Cleaning Only'),
    ('S11', 842, 'UWI', 'Inspection Only (should have minimal effect)'),
]

print("=" * 80)
print("Analysis of specific maintenance events")
print("=" * 80)

for vessel, event_day, event_type, description in test_cases:
    print(f"\n【{vessel} Day {event_day:.0f} - {event_type}】{description}")
    print("-" * 80)

    vessel_df = vt_df[vt_df['vessel'] == vessel]

    # Before: 30 days before
    before_data = vessel_df[(vessel_df['day'] >= event_day - 30) & (vessel_df['day'] < event_day)]

    # After: 30 days after
    after_data = vessel_df[(vessel_df['day'] > event_day) & (vessel_df['day'] <= event_day + 30)]

    if len(before_data) > 0:
        stw_before = before_data['stw'].mean()
        print(f"Before 30 days ({event_day-30:.0f}~{event_day:.0f}):")
        print(f"  Records: {len(before_data)}")
        print(f"  STW range: {before_data['stw'].min():.2f} ~ {before_data['stw'].max():.2f} knots")
        print(f"  STW avg: {stw_before:.2f} knots")

    if len(after_data) > 0:
        stw_after = after_data['stw'].mean()
        print(f"\nAfter 30 days ({event_day:.0f}~{event_day+30:.0f}):")
        print(f"  Records: {len(after_data)}")
        print(f"  STW range: {after_data['stw'].min():.2f} ~ {after_data['stw'].max():.2f} knots")
        print(f"  STW avg: {stw_after:.2f} knots")

    if len(before_data) > 0 and len(after_data) > 0:
        delta = stw_after - stw_before
        delta_pct = delta / stw_before * 100
        print(f"\nComparison:")
        print(f"  STW change: {delta:+.2f} knots ({delta_pct:+.2f}%)")
        print(f"  Expected: maintenance should improve STW (increase)")
        if delta > 0:
            print(f"  OK - STW increased (improved)")
        elif delta < 0:
            print(f"  NOT OK - STW decreased (degraded)")
        else:
            print(f"  - STW unchanged")

print("\n" + "=" * 80)
print("Summary: Do maintenance events improve STW?")
print("=" * 80)

# All maintenance events analysis
improvements = []

for vessel in sorted(vt_df['vessel'].unique()):
    vessel_df = vt_df[vt_df['vessel'] == vessel]
    vessel_maint = maint_df[maint_df['ship_id'] == vessel]

    for _, maint in vessel_maint.iterrows():
        event_day = float(maint['event_day'])
        event_type = maint['event_type']

        before_data = vessel_df[(vessel_df['day'] >= event_day - 30) & (vessel_df['day'] < event_day)]
        after_data = vessel_df[(vessel_df['day'] > event_day) & (vessel_df['day'] <= event_day + 30)]

        if len(before_data) >= 3 and len(after_data) >= 3:
            stw_before = before_data['stw'].mean()
            stw_after = after_data['stw'].mean()
            delta = stw_after - stw_before

            improvements.append({
                'vessel': vessel,
                'day': event_day,
                'type': event_type,
                'stw_before': stw_before,
                'stw_after': stw_after,
                'delta': delta,
                'improved': delta > 0,
            })

imp_df = pd.DataFrame(improvements)

if len(imp_df) > 0:
    improved_count = imp_df['improved'].sum()
    total = len(imp_df)
    improved_pct = improved_count / total * 100

    print(f"\nTotal maintenance events with enough data: {total}")
    print(f"STW improved: {improved_count} ({improved_pct:.1f}%)")
    print(f"STW degraded: {total - improved_count} ({100 - improved_pct:.1f}%)")
    print(f"\nAverage STW change: {imp_df['delta'].mean():+.2f} knots")

    print("\nBy maintenance type:")
    for mtype in ['DD', 'UWC+PP', 'UWC', 'PP', 'UWI+PP', 'UWI']:
        group = imp_df[imp_df['type'] == mtype]
        if len(group) > 0:
            impr = group['improved'].sum()
            tot = len(group)
            pct = impr / tot * 100
            avg_delta = group['delta'].mean()
            print(f"  {mtype:8s}: {impr:2d}/{tot:2d} improved ({pct:5.1f}%) | avg {avg_delta:+6.2f} knots")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
