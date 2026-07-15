import pandas as pd

vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)
maint = pd.read_csv('yangming-aws-summit-hackathon/maintenance.csv', low_memory=False)

vt = vt.rename(columns={'De-identification Name': 'ship_id'})
for col in ['NOON_UTC', 'WIND_SCALE', 'HOURS_FULL_SPEED']:
    if col in vt.columns:
        vt[col] = pd.to_numeric(vt[col], errors='coerce')

maint['event_day'] = pd.to_numeric(maint['event_day'], errors='coerce')

print("=== 基線窗口數據檢查 ===\n")
for ship in ['S1', 'S21', 'S23']:
    ship_vt = vt[vt['ship_id'] == ship]
    ship_maint = maint[maint['ship_id'] == ship]
    if len(ship_maint) > 0:
        last_evt = ship_maint.iloc[-1]['event_day']
        vt_max = ship_vt['NOON_UTC'].max()
        vt_3_7 = ship_vt[(ship_vt['NOON_UTC'] >= last_evt+3) & (ship_vt['NOON_UTC'] < last_evt+7)]
        vt_strict = vt_3_7[(vt_3_7['WIND_SCALE'] <= 2) & (vt_3_7['HOURS_FULL_SPEED'] >= 20)]

        print(f"{ship}:")
        print(f"  最後養護: day {last_evt}")
        print(f"  VT 數據範圍: day 0-{vt_max}")
        print(f"  3-7天窗口內筆數: {len(vt_3_7)}")
        print(f"  符合條件 (wind≤2, hours≥20): {len(vt_strict)}")
        if len(vt_strict) > 0:
            print(f"  RPM 範圍: {vt_strict['ME_AVG_RPM'].min():.1f}-{vt_strict['ME_AVG_RPM'].max():.1f}")
            print(f"  STW 範圍: {vt_strict['SPEED_THROUGH_WATER'].min():.2f}-{vt_strict['SPEED_THROUGH_WATER'].max():.2f}")
        print()

print("=== 改用更寬鬆標準試試 ===\n")
for ship in ['S1', 'S21', 'S23']:
    ship_vt = vt[vt['ship_id'] == ship]
    ship_maint = maint[maint['ship_id'] == ship]
    if len(ship_maint) > 0:
        last_evt = ship_maint.iloc[-1]['event_day']
        vt_loose = ship_vt[(ship_vt['NOON_UTC'] >= last_evt+2) & (ship_vt['NOON_UTC'] < last_evt+10)]
        vt_strict = vt_loose[(vt_loose['WIND_SCALE'] <= 3) & (vt_loose['HOURS_FULL_SPEED'] >= 18)]
        print(f"{ship} (day {last_evt}+2到10, wind≤3, hours≥18): {len(vt_strict)} 筆")
