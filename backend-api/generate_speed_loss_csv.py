#!/usr/bin/env python3
"""
从原始数据计算 speed loss CSV
1. 加载maintenance.csv和vt_fd.csv
2. 用进坞后7-14天的top 10% FOC作为baseline（按RPM bin）
3. 计算所有记录的speed loss
4. 验证维修前后speed loss是否下降
5. 输出CSV
"""
import pandas as pd
import sys
from collections import defaultdict
from statistics import median

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
OUTPUT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\speed_loss_maintenance_impact.csv"

WINDOW_DAYS = 60  # 扩大时间窗口从30天改为60天
# Baseline: 每个cycle的前15%（或最少5条）代表clean状态
BASELINE_PCT = 0.15
BASELINE_MIN = 5
MIN_DATA_POINTS = 5  # 过滤掉数据点少于5的事件

HULL_CLEAN_TYPES = {'DD', 'UWC', 'UWC+PP'}

# FOC标准化常数（来自handler.py）
LCV_VLSFO = 40.2
FUEL_COLS = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
    'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
    'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}


def calc_daily_foc(row):
    """将FOC标准化到24小时VLSFO等效"""
    hfs = float(row.get('HOURS_FULL_SPEED', 0))
    if hfs < 22:
        return None

    best_col = None
    best_val = 0
    for col, lcv in FUEL_COLS.items():
        try:
            v = float(row.get(col, 0))
            if v > best_val:
                best_val = v
                best_col = col
        except:
            pass

    if best_col is None or best_val <= 0:
        return None

    lcv = FUEL_COLS[best_col]
    vlsfo_equiv = best_val * lcv / LCV_VLSFO
    daily_foc = vlsfo_equiv / hfs * 24.0
    return daily_foc


def main():
    print("=" * 80)
    print("Generate Speed Loss CSV from raw data")
    print("=" * 80)

    # Load maintenance
    print("\nLoading maintenance.csv...")
    maint_df = pd.read_csv(MAINT_PATH)
    print(f"  Loaded {len(maint_df)} events")

    # Load and prepare vessel data
    print("Loading vt_fd.csv...")
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)
    print(f"  Raw: {len(vt_df)} records")

    # Rename columns
    vt_df.rename(columns={
        'De-identification Name': 'vessel',
        'NOON_UTC': 'day',
        'ME_AVG_RPM': 'rpm',
    }, inplace=True)

    # Filter: calm condition (wind_scale <= 4, hours >= 22)
    vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
    vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
    vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]
    print(f"  After calm filter: {len(vt_df)} records")

    # Calculate normalized FOC
    vt_df['foc'] = vt_df.apply(calc_daily_foc, axis=1)
    vt_df['rpm'] = pd.to_numeric(vt_df['rpm'], errors='coerce')

    # Clean
    vt_df = vt_df[['vessel', 'day', 'rpm', 'foc']].dropna()
    vt_df = vt_df[(vt_df['foc'] > 0) & (vt_df['rpm'] > 0)]
    print(f"  Final: {len(vt_df)} records")

    # Process each vessel
    results = []
    validation = []

    for vessel in sorted(vt_df['vessel'].unique()):
        print(f"\n{vessel}:")
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day').reset_index(drop=True)
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        # Find dry dock events
        dd_events = sorted([
            float(m['event_day'])
            for _, m in vessel_maint.iterrows()
            if m['event_type'] in HULL_CLEAN_TYPES
        ])

        if len(dd_events) == 0:
            print("  No dry dock events")
            continue

        # Build baselines: cycle의 처음 15% (또는 최소 5개)
        # 이는 DD 직후의 clean 상태를 대표함
        baselines = {}
        for i, dd_day in enumerate(dd_events):
            # cycle: DD에서 다음 DD까지
            if i < len(dd_events) - 1:
                cycle_end = dd_events[i + 1]
            else:
                cycle_end = vessel_df['day'].max() + 1

            cycle_data = vessel_df[
                (vessel_df['day'] >= dd_day) &
                (vessel_df['day'] < cycle_end)
            ].sort_values('day').reset_index(drop=True)

            if len(cycle_data) == 0:
                print(f"  DD Day {dd_day:.0f}: no cycle data")
                continue

            # Baseline: cycle의 처음 15% (또는 최소 5개)
            n_baseline = max(BASELINE_MIN, int(len(cycle_data) * BASELINE_PCT))
            baseline_data = cycle_data.iloc[:n_baseline]

            # Group by 5-RPM bins, median FOC per bin
            rpm_bins = defaultdict(list)
            for _, row in baseline_data.iterrows():
                bin_key = int(row['rpm'] // 5) * 5
                rpm_bins[bin_key].append(row['foc'])

            # Median FOC for each bin (matches handler.py method)
            baseline = {}
            for bin_key, foc_list in rpm_bins.items():
                foc_sorted = sorted(foc_list)
                baseline[bin_key] = foc_sorted[len(foc_sorted) // 2]  # median

            baselines[dd_day] = baseline
            print(f"  DD Day {dd_day:.0f}: cycle {len(cycle_data)} records, baseline from {n_baseline}, bins: {sorted(baseline.keys())}")

        # Calculate speed loss for all records
        def get_baseline_foc(day, rpm):
            # Find most recent DD before this day
            recent_dd = None
            for dd in sorted(baselines.keys()):
                if dd <= day:
                    recent_dd = dd
            if recent_dd is None:
                return None

            baseline = baselines[recent_dd]
            bin_key = int(rpm // 5) * 5
            if bin_key in baseline:
                return baseline[bin_key]

            bins = list(baseline.keys())
            if not bins:
                return None
            nearest = min(bins, key=lambda b: abs(b - bin_key))
            return baseline[nearest]

        vessel_df['baseline_foc'] = vessel_df.apply(
            lambda r: get_baseline_foc(r['day'], r['rpm']),
            axis=1
        )
        vessel_df['speed_loss_pct'] = vessel_df.apply(
            lambda r: max(0.0, (r['foc'] - r['baseline_foc']) / r['baseline_foc'] * 100)
            if r['baseline_foc'] and r['baseline_foc'] > 0 else None,
            axis=1
        )

        # For each maintenance event
        for _, maint in vessel_maint.iterrows():
            event_day = float(maint['event_day'])
            event_type = maint['event_type']

            before_w = vessel_df[(vessel_df['day'] >= event_day - WINDOW_DAYS) & (vessel_df['day'] < event_day)]
            after_w = vessel_df[(vessel_df['day'] > event_day) & (vessel_df['day'] <= event_day + WINDOW_DAYS)]

            # 只有数据点足够时才计算
            if len(before_w) >= MIN_DATA_POINTS and len(after_w) >= MIN_DATA_POINTS:
                sl_before = before_w['speed_loss_pct'].mean()
                sl_after = after_w['speed_loss_pct'].mean()
                sl_drop = sl_before - sl_after
            else:
                sl_before = None
                sl_after = None
                sl_drop = None

            results.append({
                'ship': vessel,
                'event_day': event_day,
                'event_type': event_type,
                'sl_before_30d': round(sl_before, 2) if sl_before is not None else None,
                'sl_after_30d': round(sl_after, 2) if sl_after is not None else None,
                'sl_drop': round(sl_drop, 2) if sl_drop is not None else None,
                'n_before': len(before_w),
                'n_after': len(after_w),
            })

            if sl_drop is not None:
                validation.append({
                    'vessel': vessel,
                    'event_day': event_day,
                    'event_type': event_type,
                    'improved': sl_drop > 0,
                    'sl_drop': sl_drop,
                })
                indicator = "✓" if sl_drop > 0 else "✗"
                print(f"  Day {event_day:.0f} {event_type:8s}: before={sl_before:7.2f}%, after={sl_after:7.2f}%, drop={sl_drop:7.2f}% {indicator}")

    # Output
    output_df = pd.DataFrame(results)
    output_df.to_csv(OUTPUT_PATH, index=False)

    # Validation
    print("\n" + "=" * 80)
    print("VALIDATION: Does maintenance reduce speed loss?")
    print("=" * 80)
    if len(validation) > 0:
        v_df = pd.DataFrame(validation)
        improved = v_df[v_df['improved']].shape[0]
        total = len(v_df)
        improvement_rate = improved / total * 100 if total > 0 else 0
        negative_rate = 100 - improvement_rate

        print(f"Total maintenance events with SL data: {total}")
        print(f"Events with SL improvement (drop > 0): {improved} ({improvement_rate:.1f}%)")
        print(f"Events with SL degradation (drop <= 0): {total - improved} ({negative_rate:.1f}%)")
        print(f"Average SL drop: {v_df['sl_drop'].mean():.2f}%")
        print(f"\nTarget: improvement_rate > 90%, negative_rate < 10%")
        if improvement_rate > 90:
            print("✓ VALIDATION PASSED")
        else:
            print("✗ VALIDATION FAILED - maintenance effect not clear enough")

    print(f"\nOutput saved: {OUTPUT_PATH}")
    print("=" * 80)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
