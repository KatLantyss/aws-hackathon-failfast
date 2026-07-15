"""
正確的 Speed Loss 計算 - ISO 19030 實踐
基於養護後穩態期建立基線模型
"""

import pandas as pd
import numpy as np
from numpy.polynomial import polynomial as P
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("\n" + "="*80)
print("Speed Loss 計算 - 基線模型法 (ISO 19030 實踐)")
print("="*80)

# 加載資料
vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)
maint = pd.read_csv('yangming-aws-summit-hackathon/maintenance.csv', low_memory=False)

vt = vt.rename(columns={'De-identification Name': 'ship_id'})

# 轉換數值
for col in ['NOON_UTC', 'AVG_SPEED', 'SPEED_THROUGH_WATER', 'ME_AVG_RPM',
            'WIND_SCALE', 'HOURS_FULL_SPEED', 'SEA_HEIGHT']:
    if col in vt.columns:
        vt[col] = pd.to_numeric(vt[col], errors='coerce')

maint['event_day'] = pd.to_numeric(maint['event_day'], errors='coerce')

print(f"\n加載: {vt.shape[0]} 行, {len(maint)} 筆維修事件")

# ============================================================================
# Step 1: 為每艘船建立基線模型
# ============================================================================
print("\n[Step 1] 建立基線模型...")

baseline_models = {}  # {ship_id: {'coeffs': [...], 'data_points': N}}

for ship_id in sorted(vt['ship_id'].unique()):
    ship_data = vt[vt['ship_id'] == ship_id].sort_values('NOON_UTC').reset_index(drop=True)
    ship_maint = maint[maint['ship_id'] == ship_id].sort_values('event_day')

    if len(ship_maint) == 0:
        print(f"  {ship_id}: 無維修記錄，跳過")
        continue

    # 找最後一次養護後的穩態期（30 天內、良好海況）
    # 選擇養護後最穩定的日子作為基線（代表「乾淨船」）
    last_maint_day = ship_maint.iloc[-1]['event_day']
    baseline_window = ship_data[
        (ship_data['NOON_UTC'] >= last_maint_day + 1) &  # 養護後至少 1 天
        (ship_data['NOON_UTC'] < last_maint_day + 30) &  # 30 天內
        (ship_data['WIND_SCALE'] <= 3) &                 # 風力 ≤ 3 級
        (ship_data['HOURS_FULL_SPEED'] >= 18)            # 全速 ≥ 18 小時
    ].copy()

    if len(baseline_window) < 5:
        print(f"  {ship_id}: 基線數據不足 ({len(baseline_window)} 天), 跳過")
        continue

    # 收集 (RPM, STW) 配對
    baseline_window = baseline_window.dropna(subset=['ME_AVG_RPM', 'SPEED_THROUGH_WATER'])

    rpm = baseline_window['ME_AVG_RPM'].values
    stw = baseline_window['SPEED_THROUGH_WATER'].values

    if len(rpm) < 5:
        print(f"  {ship_id}: 有效配對不足, 跳過")
        continue

    # 一階線性擬合（穩健方法）
    try:
        # 一階：STW = a·RPM + b
        coeffs_linear = np.polyfit(rpm, stw, 1)  # [a, b]

        # 計算 R²
        stw_pred = np.polyval(coeffs_linear, rpm)
        ss_res = np.sum((stw - stw_pred) ** 2)
        ss_tot = np.sum((stw - np.mean(stw)) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        baseline_models[ship_id] = {
            'slope': coeffs_linear[0],      # a
            'intercept': coeffs_linear[1],  # b
            'n_points': len(rpm),
            'r_squared': r2,
            'rpm_range': (rpm.min(), rpm.max()),
            'stw_range': (stw.min(), stw.max()),
        }

        print(f"  {ship_id}: ✓ 基線建立 (n={len(rpm)}, R²={r2:.3f})")
        print(f"           公式: STW = {coeffs_linear[0]:.4f}·RPM + {coeffs_linear[1]:.4f}")
        print(f"           範圍: RPM {rpm.min():.1f}-{rpm.max():.1f}, STW {stw.min():.2f}-{stw.max():.2f}")

    except Exception as e:
        print(f"  {ship_id}: 擬合失敗 - {e}")
        continue

# ============================================================================
# Step 2: 計算每日 Speed Loss
# ============================================================================
print("\n[Step 2] 計算每日 Speed Loss...")

results = []

for idx, row in vt.iterrows():
    ship_id = row['ship_id']
    noon_utc = row['NOON_UTC']
    rpm = row['ME_AVG_RPM']
    stw_actual = row['SPEED_THROUGH_WATER']

    # 檢查是否有基線模型
    if ship_id not in baseline_models or pd.isna(rpm) or pd.isna(stw_actual):
        continue

    model = baseline_models[ship_id]
    slope = model['slope']
    intercept = model['intercept']

    # 只在基線 RPM 範圍內計算（防止外推失敗）
    rpm_min, rpm_max = model['rpm_range']
    if rpm < (rpm_min - 2) or rpm > (rpm_max + 2):  # 允許 ±2 RPM 容差
        continue

    # 計算 V_ref（乾淨船殼下的理論 STW）
    # V_ref = slope·RPM + intercept
    v_ref = slope * rpm + intercept

    # Speed Loss
    if v_ref > 0.5:  # 避免極小的 V_ref
        speed_loss_pct = ((v_ref - stw_actual) / v_ref) * 100
    else:
        speed_loss_pct = np.nan

    results.append({
        'ship_id': ship_id,
        'NOON_UTC': noon_utc,
        'RPM': rpm,
        'V_actual': stw_actual,
        'V_ref': v_ref,
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
print(f"  Q1-Q3: {sl_df['speed_loss_pct'].quantile(0.25):.2f}% ~ {sl_df['speed_loss_pct'].quantile(0.75):.2f}%")

# 按船舶統計
print("\n按船舶統計:")
for ship_id in sorted(sl_df['ship_id'].unique()):
    ship_sl = sl_df[sl_df['ship_id'] == ship_id]['speed_loss_pct']
    print(f"  {ship_id}: avg={ship_sl.mean():.2f}%, med={ship_sl.median():.2f}%, "
          f"range=[{ship_sl.min():.1f}%, {ship_sl.max():.1f}%], n={len(ship_sl)}")

# ============================================================================
# Step 4: 異常檢測
# ============================================================================
print("\n[Step 4] 異常檢測:")

# 負 Speed Loss（污損導致速度下降反向）
negative_sl = sl_df[sl_df['speed_loss_pct'] < -5]
print(f"  負 Speed Loss (< -5%): {len(negative_sl)} 筆 (異常)")

# 極高（> 30%）
extreme_sl = sl_df[sl_df['speed_loss_pct'] > 30]
print(f"  極高 Speed Loss (> 30%): {len(extreme_sl)} 筆 (嚴重污損)")

# ============================================================================
# Save
# ============================================================================
sl_df.to_csv('speed_loss_results_correct.csv', index=False)
print(f"\n✓ 已保存至 speed_loss_results_correct.csv ({len(sl_df)} 筆)")

# 保存基線模型元數據
models_info = []
for ship_id, model in baseline_models.items():
    models_info.append({
        'ship_id': ship_id,
        'slope': model['slope'],
        'intercept': model['intercept'],
        'r_squared': model['r_squared'],
        'n_baseline_points': model['n_points'],
        'rpm_min': model['rpm_range'][0],
        'rpm_max': model['rpm_range'][1],
    })
models_df = pd.DataFrame(models_info)
models_df.to_csv('baseline_models.csv', index=False)
print(f"✓ 基線模型已保存至 baseline_models.csv")

print("\n" + "="*80 + "\n")
