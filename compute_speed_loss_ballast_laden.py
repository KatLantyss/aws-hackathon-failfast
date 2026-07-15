"""
計算 Speed Loss - 簡單統計法，分 Ballast 和 LADEN
不用基線模型，直接用歷史最高速作為參考
"""

import pandas as pd
import numpy as np
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("\n" + "="*80)
print("Speed Loss 計算 - 簡單統計法 (Ballast + LADEN 分離)")
print("="*80)

# Load data
vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)
vt = vt.rename(columns={'De-identification Name': 'ship_id'})

# Convert numeric
for col in ['NOON_UTC', 'AVG_SPEED', 'CARGO_ON_BOARD', 'WIND_SCALE', 'HOURS_FULL_SPEED']:
    vt[col] = pd.to_numeric(vt[col], errors='coerce')

print(f"\nLoaded: {vt.shape[0]} rows")

# ============================================================================
# Check cargo distribution
# ============================================================================
print("\n[Cargo Distribution]")
cargo = vt['CARGO_ON_BOARD'].dropna()
print(f"  Min: {cargo.min():.0f}, Max: {cargo.max():.0f}, Median: {cargo.median():.0f}")
print(f"  Ballast (< 100): {(vt['CARGO_ON_BOARD'] < 100).sum()} rows")
print(f"  LADEN (>= 100): {(vt['CARGO_ON_BOARD'] >= 100).sum()} rows")

# ============================================================================
# Step 1: Calculate reference speed for each condition
# ============================================================================
print("\n[Step 1] Computing reference speeds (95th percentile)...")

reference_speeds = {}

for ship_id in sorted(vt['ship_id'].unique()):
    ship_data = vt[vt['ship_id'] == ship_id]

    for condition in ['Ballast', 'LADEN']:
        # Filter by cargo and good conditions
        if condition == 'Ballast':
            filtered = ship_data[
                (ship_data['CARGO_ON_BOARD'] < 100) &
                (ship_data['WIND_SCALE'] <= 3) &
                (ship_data['HOURS_FULL_SPEED'] >= 18) &
                (ship_data['AVG_SPEED'] > 0)
            ]
        else:  # LADEN
            filtered = ship_data[
                (ship_data['CARGO_ON_BOARD'] >= 100) &
                (ship_data['WIND_SCALE'] <= 3) &
                (ship_data['HOURS_FULL_SPEED'] >= 18) &
                (ship_data['AVG_SPEED'] > 0)
            ]

        speeds = filtered['AVG_SPEED'].dropna()

        if len(speeds) >= 5:
            ref_speed = speeds.quantile(0.95)
            key = (ship_id, condition)
            reference_speeds[key] = ref_speed

print(f"  Computed {len(reference_speeds)} reference speeds")

# ============================================================================
# Step 2: Calculate daily Speed Loss
# ============================================================================
print("\n[Step 2] Computing daily Speed Loss...")

results = []

for idx, row in vt.iterrows():
    ship_id = row['ship_id']
    noon_utc = row['NOON_UTC']
    actual_speed = row['AVG_SPEED']
    cargo = row['CARGO_ON_BOARD']

    if pd.isna(actual_speed) or pd.isna(cargo):
        continue

    # Determine condition
    condition = 'Ballast' if cargo < 100 else 'LADEN'
    key = (ship_id, condition)

    if key not in reference_speeds:
        continue

    ref_speed = reference_speeds[key]

    # Calculate Speed Loss
    if actual_speed > 0 and ref_speed > 0:
        speed_loss_pct = ((ref_speed - actual_speed) / ref_speed) * 100
    else:
        speed_loss_pct = np.nan

    results.append({
        'ship_id': ship_id,
        'NOON_UTC': noon_utc,
        'condition': condition,
        'reference_speed_knots': ref_speed,
        'actual_speed_knots': actual_speed,
        'speed_loss_pct': speed_loss_pct,
    })

sl_df = pd.DataFrame(results)
sl_df = sl_df.dropna(subset=['speed_loss_pct'])

print(f"  Computed: {len(sl_df)} valid Speed Loss records")

# ============================================================================
# Step 3: Statistics
# ============================================================================
print("\n[Step 3] Speed Loss Statistics:")
print(f"  Mean: {sl_df['speed_loss_pct'].mean():.2f}%")
print(f"  Median: {sl_df['speed_loss_pct'].median():.2f}%")
print(f"  Std Dev: {sl_df['speed_loss_pct'].std():.2f}%")
print(f"  Range: {sl_df['speed_loss_pct'].min():.2f}% ~ {sl_df['speed_loss_pct'].max():.2f}%")
print(f"  Q1-Q3: {sl_df['speed_loss_pct'].quantile(0.25):.2f}% ~ {sl_df['speed_loss_pct'].quantile(0.75):.2f}%")

# By condition
print("\nBy condition:")
for cond in ['Ballast', 'LADEN']:
    cond_data = sl_df[sl_df['condition'] == cond]['speed_loss_pct']
    print(f"  {cond}: avg={cond_data.mean():.2f}%, med={cond_data.median():.2f}%, n={len(cond_data)}")

# By ship
print("\nBy ship:")
for ship_id in sorted(sl_df['ship_id'].unique()):
    ship_sl = sl_df[sl_df['ship_id'] == ship_id]['speed_loss_pct']
    print(f"  {ship_id}: avg={ship_sl.mean():.2f}%, med={ship_sl.median():.2f}%, "
          f"range=[{ship_sl.min():.1f}%, {ship_sl.max():.1f}%], n={len(ship_sl)}")

# ============================================================================
# Save
# ============================================================================
sl_df.to_csv('speed_loss_ballast_laden.csv', index=False)
print(f"\n✓ Saved to speed_loss_ballast_laden.csv ({len(sl_df)} records)")

print("\n" + "="*80 + "\n")
