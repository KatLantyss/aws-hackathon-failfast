"""
正確計算 Speed Loss - ISO 19030 標準

Speed Loss (%) = ((Reference_Speed - Actual_Speed) / Reference_Speed) × 100%

Reference_Speed = 該船在良好海況下的基準速度 (使用 95th percentile)
Actual_Speed = AVG_SPEED (對地航速)
"""

import pandas as pd
import numpy as np
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("\n" + "="*80)
print("計算 Speed Loss (ISO 19030)")
print("="*80)

# 加載資料
vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)
vt = vt.rename(columns={'De-identification Name': 'ship_id'})

# 轉換數值
vt['NOON_UTC'] = pd.to_numeric(vt['NOON_UTC'], errors='coerce')
vt['AVG_SPEED'] = pd.to_numeric(vt['AVG_SPEED'], errors='coerce')
vt['WIND_SCALE'] = pd.to_numeric(vt['WIND_SCALE'], errors='coerce')
vt['HOURS_FULL_SPEED'] = pd.to_numeric(vt['HOURS_FULL_SPEED'], errors='coerce')

print(f"\n加載: {vt.shape[0]} 行")

# ============================================================================
# Step 1: 計算每艘船的參考速度 (Reference Speed)
# ============================================================================
print("\n[Step 1] 計算參考速度...")

# 篩選良好海況條件
good_conditions = vt[
    (vt['WIND_SCALE'] <= 2) &  # 風力 ≤ 2 級
    (vt['HOURS_FULL_SPEED'] >= 22) &  # 全速 ≥ 22 小時
    (vt['AVG_SPEED'] > 0)
].copy()

print(f"  良好海況數據: {len(good_conditions)} 行")

# 按船舶計算基準速度 (95th percentile = 參考值)
reference_speeds = {}
for ship_id in vt['ship_id'].unique():
    ship_data = good_conditions[good_conditions['ship_id'] == ship_id]['AVG_SPEED']
    if len(ship_data) >= 5:
        # 用 95th percentile 作為參考速度（相當穩健的基準）
        ref_speed = ship_data.quantile(0.95)
        reference_speeds[ship_id] = ref_speed
        print(f"  {ship_id}: 參考速度 = {ref_speed:.2f} knots (基於 {len(ship_data)} 個良好海況日)")
    else:
        # 如果資料不足，用平均值
        ref_speed = ship_data.mean()
        reference_speeds[ship_id] = ref_speed
        print(f"  {ship_id}: 參考速度 = {ref_speed:.2f} knots (基於 {len(ship_data)} 個日)")

# ============================================================================
# Step 2: 計算所有日期的 Speed Loss
# ============================================================================
print("\n[Step 2] 計算 Speed Loss...")

results = []

for idx, row in vt.iterrows():
    ship_id = row['ship_id']
    noon_utc = row['NOON_UTC']
    actual_speed = row['AVG_SPEED']

    # 取得參考速度
    if ship_id not in reference_speeds:
        continue

    ref_speed = reference_speeds[ship_id]

    # 計算 Speed Loss
    if pd.notna(actual_speed) and actual_speed > 0 and ref_speed > 0:
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

print(f"  計算完成: {len(sl_df)} 筆有效 Speed Loss 資料")

# ============================================================================
# Step 3: 統計與驗證
# ============================================================================
print("\n[Step 3] Speed Loss 統計:")
print(f"  平均: {sl_df['speed_loss_pct'].mean():.2f}%")
print(f"  中位數: {sl_df['speed_loss_pct'].median():.2f}%")
print(f"  標準差: {sl_df['speed_loss_pct'].std():.2f}%")
print(f"  範圍: {sl_df['speed_loss_pct'].min():.2f}% ~ {sl_df['speed_loss_pct'].max():.2f}%")

# 按船舶統計
print("\n按船舶統計:")
for ship_id in sorted(sl_df['ship_id'].unique()):
    ship_sl = sl_df[sl_df['ship_id'] == ship_id]['speed_loss_pct']
    print(f"  {ship_id}: 平均 {ship_sl.mean():.2f}%, 中位 {ship_sl.median():.2f}%, "
          f"範圍 {ship_sl.min():.2f}% ~ {ship_sl.max():.2f}%")

# ============================================================================
# Step 4: 異常檢測
# ============================================================================
print("\n[Step 4] 異常檢測:")

# 負的 Speed Loss（實際速度 > 參考速度）= 異常或特殊情況
negative_sl = sl_df[sl_df['speed_loss_pct'] < 0]
print(f"  負 Speed Loss (異常快): {len(negative_sl)} 筆")
if len(negative_sl) > 0:
    print(f"    最快改善: {negative_sl['speed_loss_pct'].min():.2f}%")

# 極高的 Speed Loss (> 20%) = 嚴重污損或異常
extreme_sl = sl_df[sl_df['speed_loss_pct'] > 20]
print(f"  極高 Speed Loss (> 20%): {len(extreme_sl)} 筆")

# ============================================================================
# Save
# ============================================================================
sl_df.to_csv('speed_loss_results.csv', index=False)
print(f"\n✓ 已保存至 speed_loss_results.csv ({len(sl_df)} 筆)")

print("\n" + "="*80 + "\n")
