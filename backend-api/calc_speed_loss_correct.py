#!/usr/bin/env python3
"""
正确的 Speed Loss 计算：
Baseline = 进坞后 7-14 天的 top 10% FOC（最佳清洁状态）
Speed Loss = (actual_foc - baseline_foc) / baseline_foc * 100
物理意义：相对于清洁状态的污损程度

关键：
1. FOC标准化到24小时（daily_foc = foc_value / hours_full_speed * 24）
2. 过滤平静海况（wind_scale <= 4, hours_full_speed >= 22）
"""
import pandas as pd
import sys
from collections import defaultdict

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
OUTPUT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\speed_loss_maintenance_impact.csv"

WINDOW_DAYS = 30
BASELINE_START_DAY = 7   # 进坞后 7 天
BASELINE_END_DAY = 14    # 进坞后 14 天
BASELINE_PERCENTILE = 10 # 取 top 10%

# 进坞类型（定义 cycle 边界）
HULL_CLEAN_TYPES = {'DD', 'UWC', 'UWC+PP'}

# FOC标准化常数
LCV_VLSFO = 40.2
FUEL_COLS = [
    'ME_FULLSPEED_CONSUMP_HSHFO',
    'ME_FULLSPEED_CONSUMP_VLSFO',
    'ME_FULLSPEED_CONSUMP_ULSFO',
    'ME_FULLSPEED_CONSUMP_LSMGO',
    'ME_FULLSPEED_CONSUMP_BIO_HSFO'
]
FUEL_LCV = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
    'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
    'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}


def calc_daily_foc(row):
    """标准化FOC到24小时VLSFO等效"""
    hfs = float(row.get('HOURS_FULL_SPEED', 0))
    if hfs < 22:
        return None

    # 找主要燃料（最大值）
    best_col = None
    best_val = 0
    for fc in FUEL_COLS:
        try:
            v = float(row.get(fc, 0))
            if v > best_val:
                best_val = v
                best_col = fc
        except:
            pass

    if best_col is None or best_val <= 0:
        return None

    # 转换到VLSFO等效
    lcv = FUEL_LCV.get(best_col, LCV_VLSFO)
    vlsfo_equiv = best_val * lcv / LCV_VLSFO

    # 标准化到24小时
    daily_foc = vlsfo_equiv / hfs * 24.0
    return daily_foc


def main():
    print("=" * 70)
    print("Calculate Speed Loss (Correct Method)")
    print("Baseline = top 10% FOC from day 7-14 after dry dock")
    print("= best clean condition")
    print("Filter: wind_scale <= 4, hours_full_speed >= 22")
    print("=" * 70)

    # Load data
    print("\nLoading vt_fd.csv...")
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)
    vt_df.rename(columns={
        'De-identification Name': 'vessel',
        'NOON_UTC': 'day',
        'ME_AVG_RPM': 'rpm',
    }, inplace=True)

    # 过滤平静海况
    vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
    vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
    vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]

    # 计算标准化FOC
    vt_df['foc'] = vt_df.apply(calc_daily_foc, axis=1)
    vt_df['rpm'] = pd.to_numeric(vt_df['rpm'], errors='coerce')

    # 清理数据
    vt_df = vt_df[['vessel', 'day', 'rpm', 'foc']].dropna()
    vt_df = vt_df[(vt_df['foc'] > 0) & (vt_df['rpm'] > 0)]
    vt_df = vt_df.sort_values(['vessel', 'day']).reset_index(drop=True)

    print(f"Loaded {len(vt_df)} records (calm condition filtered)")

    print("Loading maintenance.csv...")
    maint_df = pd.read_csv(MAINT_PATH)
    print(f"Loaded {len(maint_df)} events")

    # Results
    results = []

    for vessel in sorted(vt_df['vessel'].unique()):
        print(f"\n{vessel}:")
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day').reset_index(drop=True)
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        if len(vessel_df) == 0:
            continue

        # Find dry dock events (DD, UWC, UWC+PP)
        dry_dock_events = sorted([
            float(m['event_day'])
            for _, m in vessel_maint.iterrows()
            if m['event_type'] in HULL_CLEAN_TYPES
        ])

        if len(dry_dock_events) == 0:
            print("  No dry dock events")
            continue

        # For each dry dock event, define cycle and baseline
        # Cycle: from one dry dock to the next
        cycle_baselines = {}  # event_day -> baseline_foc_by_rpm_bin

        for i, dd_day in enumerate(dry_dock_events):
            # Get next dry dock day (or end of data)
            if i < len(dry_dock_events) - 1:
                next_dd_day = dry_dock_events[i + 1]
            else:
                next_dd_day = vessel_df['day'].max() + 1

            # Get data for baseline window: 7-14 days after dry dock
            baseline_start = dd_day + BASELINE_START_DAY
            baseline_end = dd_day + BASELINE_END_DAY
            baseline_window = vessel_df[
                (vessel_df['day'] >= baseline_start) &
                (vessel_df['day'] <= baseline_end)
            ]

            if len(baseline_window) == 0:
                print(f"  DD Day {dd_day:.0f}: no data in baseline window (day {baseline_start:.0f}-{baseline_end:.0f})")
                continue

            # Top 10% FOC (best, lowest) for each RPM bin
            rpm_bins = defaultdict(list)
            for _, row in baseline_window.iterrows():
                bin_key = int(row['rpm'] // 5) * 5
                rpm_bins[bin_key].append(row['foc'])

            # For each bin, get the 10th percentile (lowest FOC = best condition)
            baseline_foc = {}
            for bin_key, foc_list in rpm_bins.items():
                foc_list_sorted = sorted(foc_list)
                pct_idx = max(0, int(len(foc_list_sorted) * BASELINE_PERCENTILE / 100) - 1)
                baseline_foc[bin_key] = foc_list_sorted[pct_idx]

            cycle_baselines[dd_day] = baseline_foc

            print(f"  DD Day {dd_day:.0f}: baseline from {len(baseline_window)} records in day {baseline_start:.0f}-{baseline_end:.0f}")
            print(f"    RPM bins: {sorted(baseline_foc.keys())}")
            print(f"    Baseline FOC: {baseline_foc}")

        # Calculate speed loss for all records
        def get_baseline_foc(day, rpm):
            """Get baseline FOC for this day and RPM (from most recent dry dock)"""
            # Find the most recent dry dock before this day
            recent_dd = None
            for dd_day in sorted(cycle_baselines.keys()):
                if dd_day <= day:
                    recent_dd = dd_day
                else:
                    break

            if recent_dd is None:
                return None

            baseline = cycle_baselines[recent_dd]
            bin_key = int(rpm // 5) * 5

            if bin_key in baseline:
                return baseline[bin_key]

            # Find nearest bin
            bins = list(baseline.keys())
            if not bins:
                return None
            nearest = min(bins, key=lambda b: abs(b - bin_key))
            return baseline[nearest]

        vessel_df['baseline_foc'] = vessel_df.apply(
            lambda row: get_baseline_foc(row['day'], row['rpm']),
            axis=1
        )
        vessel_df['speed_loss_pct'] = vessel_df.apply(
            lambda row: (row['foc'] - row['baseline_foc']) / row['baseline_foc'] * 100
            if row['baseline_foc'] and row['baseline_foc'] > 0 else None,
            axis=1
        )

        # For each maintenance event, calculate before/after speed loss
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

    # Output and verify
    output_df = pd.DataFrame(results)

    print("\n" + "=" * 70)
    print("Verification: Does maintenance reduce Speed Loss?")
    print("=" * 70)

    valid_drops = output_df[output_df['sl_drop'].notna()]
    if len(valid_drops) > 0:
        positive_drops = valid_drops[valid_drops['sl_drop'] > 0]
        improvement_rate = len(positive_drops) / len(valid_drops) * 100

        print(f"Total events with SL data: {len(valid_drops)}")
        print(f"Events with SL improvement (drop > 0): {len(positive_drops)} ({improvement_rate:.1f}%)")
        print(f"Average SL improvement: {positive_drops['sl_drop'].mean():.2f}% (when positive)")
        print(f"Average SL change (all): {valid_drops['sl_drop'].mean():.2f}%")

        # Negative value rate
        negative_rate = (len(valid_drops) - len(positive_drops)) / len(valid_drops) * 100
        print(f"Negative value rate: {negative_rate:.1f}% (should be < 10%)")

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
