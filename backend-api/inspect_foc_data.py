#!/usr/bin/env python3
"""
检查具体 DD 事件前后的原始 FOC 数据
FOC = Fuel Oil Consumption 燃油消耗
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"

# FOC标准化常数
LCV_VLSFO = 40.2
FUEL_COLS = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
    'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
    'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}


def calc_daily_foc(row):
    """Daily FOC = (ME_FULLSPEED_CONSUMP_VLSFO / HOURS_FULL_SPEED) × 24"""
    hfs = float(row.get('HOURS_FULL_SPEED', 0))
    if hfs < 22:
        return None, None

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
        return None, None

    lcv = FUEL_COLS[best_col]
    vlsfo_equiv = best_val * lcv / LCV_VLSFO
    daily_foc = vlsfo_equiv / hfs * 24.0

    return round(daily_foc, 2), best_col.replace('ME_FULLSPEED_CONSUMP_', '')


def main():
    print("Loading data...")
    maint_df = pd.read_csv(MAINT_PATH)
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)

    # 检查S11 Day 1132的DD事件前后数据
    vessel = 'S11'
    dd_day = 1132.0
    window = 30

    print(f"\n{'='*80}")
    print(f"Inspecting {vessel} DD event on Day {dd_day}")
    print(f"{'='*80}")

    # 获取该船的数据
    vessel_df = vt_df[vt_df['De-identification Name'] == vessel].copy()
    print(f"\nTotal records for {vessel}: {len(vessel_df)}")

    # 显示原始列
    print(f"\nColumns in vt_fd.csv:")
    cols = list(vt_df.columns)
    for i, col in enumerate(cols):
        if i % 3 == 0:
            print()
        print(f"  {col:40s}", end="")

    # 获取DD事件前后的数据
    before_data = vessel_df[(vessel_df['NOON_UTC'] >= dd_day - window) & (vessel_df['NOON_UTC'] < dd_day)]
    after_data = vessel_df[(vessel_df['NOON_UTC'] > dd_day) & (vessel_df['NOON_UTC'] <= dd_day + window)]

    print(f"\n\n【DD事件前 {window} 天】(Day {dd_day - window} ~ {dd_day}):")
    print(f"Records: {len(before_data)}")
    if len(before_data) > 0:
        print(f"\n{'Day':<8} {'RPM':<8} {'Hours':<8} {'Fuel_Col':<20} {'Raw_Val':<12} {'Daily_FOC':<12}")
        print("-" * 80)

        foc_values_before = []
        for _, row in before_data.iterrows():
            day = row['NOON_UTC']
            rpm = row.get('ME_AVG_RPM', '')
            hours = row.get('HOURS_FULL_SPEED', '')

            daily_foc, fuel_type = calc_daily_foc(row)

            if daily_foc:
                foc_values_before.append(daily_foc)
                best_col = f'ME_FULLSPEED_CONSUMP_{fuel_type}'
                try:
                    raw_val = float(row.get(best_col, 0))
                except:
                    raw_val = 0
                print(f"{day:<8.0f} {rpm:<8.1f} {hours:<8.1f} {fuel_type:<20s} {raw_val:<12.2f} {daily_foc:<12.2f}")

        if foc_values_before:
            avg_before = sum(foc_values_before) / len(foc_values_before)
            print(f"\nAverage Daily FOC (before): {avg_before:.2f}")

    print(f"\n【DD事件后 {window} 天】(Day {dd_day} ~ {dd_day + window}):")
    print(f"Records: {len(after_data)}")
    if len(after_data) > 0:
        print(f"\n{'Day':<8} {'RPM':<8} {'Hours':<8} {'Fuel_Col':<20} {'Raw_Val':<12} {'Daily_FOC':<12}")
        print("-" * 80)

        foc_values_after = []
        for _, row in after_data.iterrows():
            day = row['NOON_UTC']
            rpm = row.get('ME_AVG_RPM', '')
            hours = row.get('HOURS_FULL_SPEED', '')

            daily_foc, fuel_type = calc_daily_foc(row)

            if daily_foc:
                foc_values_after.append(daily_foc)
                best_col = f'ME_FULLSPEED_CONSUMP_{fuel_type}'
                try:
                    raw_val = float(row.get(best_col, 0))
                except:
                    raw_val = 0
                print(f"{day:<8.0f} {rpm:<8.1f} {hours:<8.1f} {fuel_type:<20s} {raw_val:<12.2f} {daily_foc:<12.2f}")

        if foc_values_after:
            avg_after = sum(foc_values_after) / len(foc_values_after)
            print(f"\nAverage Daily FOC (after): {avg_after:.2f}")

    # 对比
    if foc_values_before and foc_values_after:
        avg_before = sum(foc_values_before) / len(foc_values_before)
        avg_after = sum(foc_values_after) / len(foc_values_after)
        improvement = (avg_before - avg_after) / avg_before * 100

        print(f"\n{'='*80}")
        print(f"DD 维修效果:")
        print(f"  Before avg: {avg_before:.2f} ton/day")
        print(f"  After avg:  {avg_after:.2f} ton/day")
        print(f"  Improvement: {improvement:.2f}% ({'✓' if improvement > 0 else '✗'})")
        print(f"{'='*80}")

    # 也检查一个UWI事件（仅检查，应该没改善）
    print(f"\n\n【对比：UWI 事件（仅检查，无物理干预）】")
    uwi_event = maint_df[(maint_df['ship_id'] == vessel) & (maint_df['event_type'] == 'UWI')].iloc[0] if any(maint_df['event_type'] == 'UWI') else None

    if uwi_event is not None:
        uwi_day = float(uwi_event['event_day'])
        print(f"{vessel} UWI event on Day {uwi_day}")

        before_uwi = vessel_df[(vessel_df['NOON_UTC'] >= uwi_day - window) & (vessel_df['NOON_UTC'] < uwi_day)]
        after_uwi = vessel_df[(vessel_df['NOON_UTC'] > uwi_day) & (vessel_df['NOON_UTC'] <= uwi_day + window)]

        foc_before_uwi = []
        foc_after_uwi = []

        for _, row in before_uwi.iterrows():
            daily_foc, _ = calc_daily_foc(row)
            if daily_foc:
                foc_before_uwi.append(daily_foc)

        for _, row in after_uwi.iterrows():
            daily_foc, _ = calc_daily_foc(row)
            if daily_foc:
                foc_after_uwi.append(daily_foc)

        if foc_before_uwi and foc_after_uwi:
            avg_before_uwi = sum(foc_before_uwi) / len(foc_before_uwi)
            avg_after_uwi = sum(foc_after_uwi) / len(foc_after_uwi)
            improvement_uwi = (avg_before_uwi - avg_after_uwi) / avg_before_uwi * 100

            print(f"  Before avg: {avg_before_uwi:.2f} ton/day")
            print(f"  After avg:  {avg_after_uwi:.2f} ton/day")
            print(f"  Change: {improvement_uwi:.2f}% (should be ~0% since UWI has no intervention)")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
