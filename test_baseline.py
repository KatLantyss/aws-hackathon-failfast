import pandas as pd
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)
maint = pd.read_csv('yangming-aws-summit-hackathon/maintenance.csv', low_memory=False)

vt = vt.rename(columns={'De-identification Name': 'ship_id'})
for col in ['NOON_UTC', 'WIND_SCALE', 'HOURS_FULL_SPEED']:
    vt[col] = pd.to_numeric(vt[col], errors='coerce')
maint['event_day'] = pd.to_numeric(maint['event_day'], errors='coerce')

print("=== Test window parameters ===\n")

tests = [
    ("narrow (3-7day, wind<=2, hrs>=20)", 3, 7, 2, 20),
    ("mid (2-10day, wind<=3, hrs>=18)", 2, 10, 3, 18),
    ("loose (1-30day, wind<=4, hrs>=18)", 1, 30, 4, 18),
]

for label, day_min, day_max, wind_max, hrs_min in tests:
    print(f"\n{label}:")
    for ship in ['S1', 'S21', 'S23']:
        ship_vt = vt[vt['ship_id'] == ship]
        ship_maint = maint[maint['ship_id'] == ship]
        if len(ship_maint) > 0:
            last_evt = ship_maint.iloc[-1]['event_day']
            window = ship_vt[(ship_vt['NOON_UTC'] >= last_evt+day_min) &
                            (ship_vt['NOON_UTC'] < last_evt+day_max) &
                            (ship_vt['WIND_SCALE'] <= wind_max) &
                            (ship_vt['HOURS_FULL_SPEED'] >= hrs_min)]
            n = len(window.dropna(subset=['ME_AVG_RPM', 'SPEED_THROUGH_WATER']))
            print(f"  {ship}: {n} points")
