"""
Regress fuel consumption vs speed loss for each ship.
Output: fuel_speed_loss_coefficients.csv with per-ship slope, intercept, R².
"""
import pandas as pd
import numpy as np
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# LCV for VLSFO equivalent conversion
LCV = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
    'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
    'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}
VLSFO_LCV = 40.2
fuel_cols = list(LCV.keys())

# Load data
print("Loading vt_fd.csv...")
vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)
print(f"  vt_fd: {vt.shape[0]} rows")

print("Loading speed_loss_results.csv...")
sl = pd.read_csv('speed_loss_results.csv')
print(f"  speed_loss: {sl.shape[0]} rows")

# Rename columns for merge
vt = vt.rename(columns={'De-identification Name': 'ship_id'})

# Convert numeric columns
for col in ['WIND_SCALE', 'HOURS_FULL_SPEED', 'NOON_UTC'] + fuel_cols:
    if col in vt.columns:
        vt[col] = pd.to_numeric(vt[col], errors='coerce')

sl['NOON_UTC'] = pd.to_numeric(sl['NOON_UTC'], errors='coerce')
sl['speed_loss_pct'] = pd.to_numeric(sl['speed_loss_pct'], errors='coerce')

# Filter vt_fd for stable conditions (same as predict criteria)
vt_stable = vt[(vt['WIND_SCALE'] <= 4) & (vt['HOURS_FULL_SPEED'] >= 22)].copy()
print(f"  Stable conditions: {vt_stable.shape[0]} rows")

# Compute VLSFO equivalent daily fuel (標準化為 24 小時)
def get_daily_fuel(row):
    hours_fs = row.get('HOURS_FULL_SPEED')
    if pd.isna(hours_fs) or hours_fs < 1:
        return np.nan

    for col in fuel_cols:
        v = row.get(col)
        if pd.notna(v) and v > 0:
            # 轉換為 VLSFO 當量
            vlsfo_equiv = v * (LCV[col] / VLSFO_LCV)
            # Daily FOC = (消耗 / 全速小時) × 24
            daily_foc = (vlsfo_equiv / hours_fs) * 24
            return daily_foc
    return np.nan

vt_stable['daily_fuel_vlsfo'] = vt_stable.apply(get_daily_fuel, axis=1)
vt_stable = vt_stable.dropna(subset=['daily_fuel_vlsfo'])
vt_stable = vt_stable[vt_stable['daily_fuel_vlsfo'] > 10]  # sanity filter
print(f"  With valid fuel: {vt_stable.shape[0]} rows")

# Merge with speed loss
merged = vt_stable.merge(
    sl[['ship_id', 'NOON_UTC', 'speed_loss_pct']].drop_duplicates(),
    on=['ship_id', 'NOON_UTC'],
    how='inner'
)
merged = merged.dropna(subset=['speed_loss_pct'])
# Filter extreme speed loss outliers
merged = merged[(merged['speed_loss_pct'] > -10) & (merged['speed_loss_pct'] < 30)]
print(f"  Merged with speed loss: {merged.shape[0]} rows")

# Regression per ship
results = []
print("\n" + "="*70)
print(f"{'Ship':<6} {'N':>5} {'Baseline':>10} {'Slope':>10} {'R²':>8} {'Interp'}")
print("="*70)

for ship_id in sorted(merged['ship_id'].unique()):
    ship_data = merged[merged['ship_id'] == ship_id]
    
    x = ship_data['speed_loss_pct'].values
    y = ship_data['daily_fuel_vlsfo'].values
    
    if len(x) < 10:
        print(f"{ship_id:<6} {'SKIP - too few points'}")
        continue
    
    # numpy linear regression
    A = np.vstack([x, np.ones(len(x))]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    
    # R²
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    
    # Interpretation: slope = MT/day per 1% speed loss
    # As percentage of baseline: pct_per_sl = slope / intercept * 100
    pct_per_sl = (slope / intercept * 100) if intercept > 0 else 0
    
    results.append({
        'ship_id': ship_id,
        'n_points': len(x),
        'baseline_fuel_mt': round(intercept, 2),
        'slope_mt_per_pct': round(slope, 3),
        'r_squared': round(r2, 4),
        'pct_increase_per_sl_pct': round(pct_per_sl, 2),
    })
    
    print(f"{ship_id:<6} {len(x):>5} {intercept:>10.2f} {slope:>10.3f} {r2:>8.4f}   每%SL → 油耗+{pct_per_sl:.2f}%")

print("="*70)

# Summary
df = pd.DataFrame(results)
avg_pct = df['pct_increase_per_sl_pct'].mean()
print(f"\n全船隊平均: 每 1% Speed Loss → 油耗增加 {avg_pct:.2f}%")
print(f"  (對比之前硬編碼的 1.8%)")
print(f"  (對比理論立方律的 ~3%)")

# Save
df.to_csv('fuel_speed_loss_coefficients.csv', index=False)
print(f"\n✓ 結果已保存至 fuel_speed_loss_coefficients.csv")
print(f"\n每艘船可用: 超額成本 = slope × speed_loss% × $620 × 30天")
print(f"例如 {results[0]['ship_id']}: slope={results[0]['slope_mt_per_pct']}, SL=5% → ${round(results[0]['slope_mt_per_pct'] * 5 * 620 * 30)}/月")
