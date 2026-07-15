"""
計算 Speed Loss - 最簡單版本
直接用歷史 95 percentile 最高速作為參考
"""

import pandas as pd
import numpy as np
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("\n" + "="*80)
print("Speed Loss 計算 - 簡單統計法")
print("="*80)

# Load
vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)
vt = vt.rename(columns={'De-identification Name': 'ship_id'})

for col in ['NOON_UTC', 'AVG_SPEED', 'WIND_SCALE', 'HOURS_FULL_SPEED']:
    vt[col] = pd.to_numeric(vt[col], errors='coerce')

print(f"\nLoaded: {vt.shape[0]} rows")

# ============================================================================
# Step 1: Reference speed (95th percentile per ship, good conditions)
# ============================================================================
print("\n[Step 1] Computing reference speeds...")

reference_speeds = {}

for ship_id in sorted(vt['ship_id'].unique()):
    ship_data = vt[vt['ship_id'] == ship_id]

    # Good conditions: wind<=3, hours>=18, speed>0
    good = ship_data[
        (ship_data['WIND_SCALE'] <= 3) &
        (ship_data['HOURS_FULL_SPEED'] >= 18) &
        (ship_data['AVG_SPEED'] > 0)
    ]

    speeds = good['AVG_SPEED'].dropna()

    if len(speeds) >= 5:
        ref_speed = speeds.quantile(0.95)
        reference_speeds[ship_id] = ref_speed
        print(f"  {ship_id}: ref_speed = {ref_speed:.2f} knots (n={len(speeds)})")

# ============================================================================
# Step 2: Calculate Speed Loss
# ============================================================================
print("\n[Step 2] Computing Speed Loss...")

results = []

for idx, row in vt.iterrows():
    ship_id = row['ship_id']
    noon_utc = row['NOON_UTC']
    actual_speed = row['AVG_SPEED']

    if ship_id not in reference_speeds or pd.isna(actual_speed):
        continue

    ref_speed = reference_speeds[ship_id]

    if actual_speed > 0 and ref_speed > 0:
        speed_loss_pct = ((ref_speed - actual_speed) / ref_speed) * 100
    else:
        speed_loss_pct = np.nan

    results.append({
        'ship_id': ship_id,
        'NOON_UTC': noon_utc,
        'reference_speed_knots': ref_speed,
        'actual_speed_knots': actual_speed,
        'speed_loss_pct': speed_loss_pct,
    })

sl_df = pd.DataFrame(results)
sl_df = sl_df.dropna(subset=['speed_loss_pct'])

print(f"  Computed: {len(sl_df)} records")

# ============================================================================
# Step 3: Statistics
# ============================================================================
print("\n[Step 3] Speed Loss Statistics:")
print(f"  Mean: {sl_df['speed_loss_pct'].mean():.2f}%")
print(f"  Median: {sl_df['speed_loss_pct'].median():.2f}%")
print(f"  Std Dev: {sl_df['speed_loss_pct'].std():.2f}%")
print(f"  Range: {sl_df['speed_loss_pct'].min():.2f}% ~ {sl_df['speed_loss_pct'].max():.2f}%")
print(f"  Q1-Q3: {sl_df['speed_loss_pct'].quantile(0.25):.2f}% ~ {sl_df['speed_loss_pct'].quantile(0.75):.2f}%")

print("\nBy ship:")
for ship_id in sorted(sl_df['ship_id'].unique()):
    ship_sl = sl_df[sl_df['ship_id'] == ship_id]['speed_loss_pct']
    print(f"  {ship_id}: avg={ship_sl.mean():.2f}%, med={ship_sl.median():.2f}%, n={len(ship_sl)}")

# ============================================================================
# Save
# ============================================================================
sl_df.to_csv('speed_loss_simple.csv', index=False)
print(f"\n✓ Saved to speed_loss_simple.csv ({len(sl_df)} records)")

print("\n" + "="*80 + "\n")
