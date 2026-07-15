#!/usr/bin/env python3
"""
用 baseline 方式计算 speed loss，验证维修事件改善
"""
import pandas as pd
import sys
from collections import defaultdict
from statistics import median

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
OUTPUT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\speed_loss_maintenance_impact.csv"

WINDOW_DAYS = 30

# Maintenance types that define cycle boundaries (hull cleaning)
HULL_CLEAN_TYPES = {'DD', 'UWC', 'UWC+PP'}


def main():
    print("=" * 70)
    print("Calculate Speed Loss using Baseline Method")
    print("=" * 70)

    # Load data
    print("\nLoading vt_fd.csv...")
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)
    vt_df.rename(columns={
        'De-identification Name': 'vessel',
        'NOON_UTC': 'day',
        'ME_AVG_RPM': 'rpm',
        'ME_FULLSPEED_CONSUMP_VLSFO': 'foc'
    }, inplace=True)
    vt_df = vt_df[['vessel', 'day', 'rpm', 'foc']].dropna()
    vt_df['foc'] = pd.to_numeric(vt_df['foc'], errors='coerce')
    vt_df['rpm'] = pd.to_numeric(vt_df['rpm'], errors='coerce')
    vt_df = vt_df[(vt_df['foc'] > 0) & (vt_df['rpm'] > 0)].dropna()
    print(f"Loaded {len(vt_df)} records")

    print("Loading maintenance.csv...")
    maint_df = pd.read_csv(MAINT_PATH)
    print(f"Loaded {len(maint_df)} events")

    # For each vessel, calculate baseline and speed loss
    results = []

    for vessel in sorted(vt_df['vessel'].unique()):
        print(f"\n{vessel}:")
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day')
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        if len(vessel_df) == 0:
            continue

        # Identify cycle boundaries (DD, UWC, UWC+PP events)
        cycle_boundaries = sorted([
            float(m['event_day'])
            for _, m in vessel_maint.iterrows()
            if m['event_type'] in HULL_CLEAN_TYPES
        ])

        def get_cycle_index(day):
            """Which cycle does this day belong to"""
            idx = 0
            for bd in cycle_boundaries:
                if day >= bd:
                    idx += 1
            return idx

        # Assign cycle to each record
        vessel_df = vessel_df.copy()
        vessel_df['cycle'] = vessel_df['day'].apply(get_cycle_index)

        # Build baseline for each cycle: first 15% (min 5 records)
        cycle_baselines = {}
        for cycle_idx in vessel_df['cycle'].unique():
            cycle_data = vessel_df[vessel_df['cycle'] == cycle_idx].sort_values('day')
            n_baseline = max(5, len(cycle_data) // 7)  # ~15%
            baseline_subset = cycle_data.iloc[:n_baseline]

            # Group by 5-RPM bins, calculate median FOC
            rpm_bins = defaultdict(list)
            for _, row in baseline_subset.iterrows():
                bin_key = int(row['rpm'] // 5) * 5
                rpm_bins[bin_key].append(row['foc'])

            baseline = {k: round(median(v), 2) for k, v in rpm_bins.items()}
            cycle_baselines[cycle_idx] = baseline
            print(f"  Cycle {cycle_idx}: {len(cycle_data)} records, baseline from {n_baseline} records")
            print(f"    RPM bins: {sorted(baseline.keys())}, FOC baseline: {baseline}")

        # Calculate speed loss for all records
        def get_baseline_foc(cycle_idx, rpm):
            bl = cycle_baselines.get(cycle_idx, {})
            if not bl:
                return None
            bin_key = int(rpm // 5) * 5
            if bin_key in bl:
                return bl[bin_key]
            # Find nearest bin
            bins = list(bl.keys())
            if not bins:
                return None
            nearest = min(bins, key=lambda b: abs(b - bin_key))
            return bl[nearest]

        vessel_df['baseline_foc'] = vessel_df.apply(
            lambda row: get_baseline_foc(row['cycle'], row['rpm']),
            axis=1
        )
        vessel_df['speed_loss_pct'] = vessel_df.apply(
            lambda row: (row['foc'] - row['baseline_foc']) / row['baseline_foc'] * 100
            if row['baseline_foc'] and row['baseline_foc'] > 0 else None,
            axis=1
        )

        # For each maintenance event, calculate before/after SL
        for _, maint in vessel_maint.iterrows():
            event_day = float(maint['event_day'])
            event_type = maint['event_type']

            before_window = vessel_df[
                (vessel_df['day'] >= event_day - WINDOW_DAYS) &
                (vessel_df['day'] < event_day)
            ]
            after_window = vessel_df[
                (vessel_df['day'] > event_day) &
                (vessel_df['day'] <= event_day + WINDOW_DAYS)
            ]

            sl_before = before_window['speed_loss_pct'].mean() if len(before_window) > 0 else None
            sl_after = after_window['speed_loss_pct'].mean() if len(after_window) > 0 else None
            sl_drop = (sl_before - sl_after) if (sl_before is not None and sl_after is not None) else None

            results.append({
                'ship': vessel,
                'event_day': event_day,
                'event_type': event_type,
                'sl_before_30d': round(sl_before, 2) if sl_before is not None else None,
                'sl_after_30d': round(sl_after, 2) if sl_after is not None else None,
                'sl_drop': round(sl_drop, 2) if sl_drop is not None else None,
                'n_before': len(before_window),
                'n_after': len(after_window),
            })

            if sl_drop is not None:
                indicator = "✓" if sl_drop > 0 else "✗"
                print(f"  Day {event_day:.0f} {event_type:8s}: before={sl_before:6.2f}%, after={sl_after:6.2f}%, drop={sl_drop:6.2f}% {indicator}")

    # Output
    output_df = pd.DataFrame(results)

    # Verify improvements
    print("\n" + "=" * 70)
    print("Verification: Does maintenance reduce Speed Loss?")
    print("=" * 70)
    valid_drops = output_df[output_df['sl_drop'].notna()]
    positive_drops = valid_drops[valid_drops['sl_drop'] > 0]
    improvement_rate = len(positive_drops) / len(valid_drops) * 100 if len(valid_drops) > 0 else 0

    print(f"Total events with SL data: {len(valid_drops)}")
    print(f"Events with SL improvement (drop > 0): {len(positive_drops)} ({improvement_rate:.1f}%)")
    print(f"Average SL improvement: {positive_drops['sl_drop'].mean():.2f}% (when positive)")
    print(f"Average SL change (all): {valid_drops['sl_drop'].mean():.2f}%")

    # Save
    output_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nOutput saved: {OUTPUT_PATH}")
    print("=" * 70)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
