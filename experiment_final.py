"""
最終優化實驗
測試：
1. 加入 S21-S23 有標籤行到訓練集
2. Sample weighting (穩態=1.0, 非穩態=0.3)
3. RPM³ 直接特徵
4. NOON_UTC (捕捉長期退化)
5. 退化速率特徵
6. 同事件內平滑後處理
7. Speed Loss 特徵
"""

import pandas as pd
import numpy as np
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold
import warnings
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
warnings.filterwarnings('ignore')

print("\n" + "="*80)
print("最終優化實驗")
print("="*80)

# ============================================================================
# 加載全部數據
# ============================================================================
train_df = pd.read_csv('data_train_with_maintenance.csv', low_memory=False)
validate_df = pd.read_csv('data_validate_with_maintenance.csv', low_memory=False)
test_df = pd.read_csv('data_test_with_maintenance.csv', low_memory=False)

# Speed Loss
try:
    sl_df = pd.read_csv('speed_loss_results.csv')
    sl_df['NOON_UTC'] = pd.to_numeric(sl_df['NOON_UTC'], errors='coerce')
    sl_df['speed_loss_pct'] = pd.to_numeric(sl_df['speed_loss_pct'], errors='coerce')
    sl_df = sl_df[(sl_df['speed_loss_pct'] > -30) & (sl_df['speed_loss_pct'] < 50)]
    HAS_SL = True
except:
    HAS_SL = False

# 數值轉換
num_cols = ['WIND_SCALE', 'HOURS_FULL_SPEED', 'ME_AVG_RPM', 'PROPELLER_SPEED',
            'SPEED_THROUGH_WATER', 'AVG_SPEED', 'DISPLACEMENT', 'NOON_UTC',
            'FORE_DRAFT', 'AFTER_DRAFT', 'MID_DRAFT', 'CARGO_ON_BOARD',
            'WIND_SPEED', 'WIND_DIRECTION', 'SEA_HEIGHT', 'SEA_DIRECTION',
            'SWELL_HEIGHT', 'SWELL_DIRECTION', 'SEA_WATER_TEMP', 'WATER_DEPTH',
            'TOTAL_DISTANCE', 'SEA_SPEED_DISTANCE', 'DIFF_STW_SOG_SLIP',
            'FULL_SPD_STW_SLIP', 'HOURS_TOTAL', 'DAYS_SINCE_LAST_MAINT', 'LAST_MAINT_TYPE']

for df in [train_df, validate_df, test_df]:
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

# 目標計算
LCV = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2, 'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2, 'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}
VLSFO_LCV = 40.2
target_cols = list(LCV.keys())

def compute_targets(df):
    results = []
    for idx in df.index:
        hours_fs = df.loc[idx, 'HOURS_FULL_SPEED']
        if pd.isna(hours_fs) or hours_fs < 1:
            continue
        for col in target_cols:
            try:
                v = float(df.loc[idx, col])
                if not np.isnan(v) and v > 0:
                    daily_foc = v * (LCV[col] / VLSFO_LCV) / hours_fs * 24
                    results.append({'orig_idx': idx, 'daily_foc': daily_foc})
                    break
            except (ValueError, TypeError):
                continue
    return pd.DataFrame(results)

# ============================================================================
# 準備不同訓練策略的數據
# ============================================================================
print("\n準備數據...")

W1_SHIPS = ['S1','S2','S3','S4','S5','S6','S7','S8','S21']

# 策略 A: 只用 S1-S12 穩態 (原版 v4)
train_strict = train_df[(train_df['WIND_SCALE'] <= 4) & (train_df['HOURS_FULL_SPEED'] >= 22)].reset_index(drop=True)

# 策略 B: S1-S12 + S21-S23有標籤 (穩態)
val_strict = validate_df[(validate_df['WIND_SCALE'] <= 4) & (validate_df['HOURS_FULL_SPEED'] >= 22)].reset_index(drop=True)
combined_strict = pd.concat([train_strict, val_strict], ignore_index=True)

# 策略 C: S1-S12 全部 + sample weighting
train_all = train_df.copy()  # 不篩選

# 策略 D: S1-S12 + S21-S23 全部 + sample weighting
combined_all = pd.concat([train_df, validate_df], ignore_index=True)

print(f"  策略A (S1-12 穩態): {len(train_strict)}")
print(f"  策略B (S1-12+S21-23 穩態): {len(combined_strict)}")
print(f"  策略C (S1-12 全部): {len(train_all)}")
print(f"  策略D (全部): {len(combined_all)}")

# 驗證集: 用 Leave-out 方式 — B/D 策略的驗證用 CV
# 但為了公平比較，統一用 S21-S23 穩態行做最終驗證
# 策略B/D的驗證改用 5-Fold CV 在合併集上

# ============================================================================
# 加入進階特徵
# ============================================================================
def add_features(df):
    df = df.copy()
    rpm = df['ME_AVG_RPM'].clip(lower=1)
    stw = df['SPEED_THROUGH_WATER'].clip(lower=1)
    disp = df['DISPLACEMENT'].clip(lower=1)

    # RPM³ (直接物理特徵)
    df['RPM_CUBED'] = (rpm / 100)**3

    # 物理基線
    C = df['ship_id'].apply(lambda s: 332.0 if s in W1_SHIPS else 315.0)
    df['PHYSICS_FOC'] = C * (rpm / 100)**3 * (disp / 100000)**(2/3)

    # Power-Speed ratio (阻力代理)
    df['POWER_SPEED_RATIO'] = (rpm / 100)**3 / (stw / 10)**3

    # 退化速率
    days = df['DAYS_SINCE_LAST_MAINT'].clip(lower=1)
    df['DAYS_SINCE_MAINT_SQRT'] = np.sqrt(days)

    # NOON_UTC (長期趨勢)
    df['NOON_UTC_NORM'] = df['NOON_UTC'] / 1825  # 標準化到 0~1 (5年)

    # Speed Loss
    if HAS_SL:
        sl_merge = sl_df[['ship_id', 'NOON_UTC', 'speed_loss_pct']].copy()
        df = df.merge(sl_merge, on=['ship_id', 'NOON_UTC'], how='left', suffixes=('', '_sl'))
        if 'speed_loss_pct_sl' in df.columns:
            df['speed_loss_pct'] = df['speed_loss_pct_sl'].fillna(0)
            df.drop(columns=['speed_loss_pct_sl'], inplace=True, errors='ignore')
        elif 'speed_loss_pct' not in df.columns:
            df['speed_loss_pct'] = 0
        else:
            df['speed_loss_pct'] = df['speed_loss_pct'].fillna(0)
    else:
        df['speed_loss_pct'] = 0

    return df

train_strict = add_features(train_strict)
combined_strict = add_features(combined_strict)
train_all = add_features(train_all)
combined_all = add_features(combined_all)
val_strict_eval = add_features(val_strict.copy())  # 用於統一評估

# ============================================================================
# 特徵列表
# ============================================================================
BASE = [
    'SEA_SPEED_DISTANCE', 'TOTAL_DISTANCE', 'ME_AVG_RPM', 'PROPELLER_SPEED',
    'HOURS_TOTAL', 'FORE_DRAFT', 'AFTER_DRAFT', 'MID_DRAFT', 'DISPLACEMENT',
    'CARGO_ON_BOARD', 'AVG_SPEED', 'SPEED_THROUGH_WATER', 'DIFF_STW_SOG_SLIP',
    'FULL_SPD_STW_SLIP', 'WIND_SCALE', 'WIND_SPEED', 'WIND_DIRECTION',
    'SEA_HEIGHT', 'SEA_DIRECTION', 'SWELL_HEIGHT', 'SWELL_DIRECTION',
    'SEA_WATER_TEMP', 'WATER_DEPTH', 'DAYS_SINCE_LAST_MAINT', 'LAST_MAINT_TYPE',
]

ENHANCED = BASE + ['speed_loss_pct', 'RPM_CUBED', 'POWER_SPEED_RATIO',
                   'DAYS_SINCE_MAINT_SQRT', 'NOON_UTC_NORM']

# ============================================================================
# 跑實驗
# ============================================================================
print("\n" + "="*80)
print("實驗")
print("="*80)

def train_and_evaluate(train_data, val_data, features, sample_weights=None, exp_name=""):
    """訓練 ensemble 並在驗證集上評估"""
    available = [f for f in features if f in train_data.columns and f in val_data.columns]

    train_targets_local = compute_targets(train_data)
    val_targets_local = compute_targets(val_data)

    if len(train_targets_local) == 0 or len(val_targets_local) == 0:
        return None

    X_train = train_data.loc[train_targets_local['orig_idx'].values, available].copy().reset_index(drop=True)
    y_train = train_targets_local['daily_foc'].values
    X_val = val_data.loc[val_targets_local['orig_idx'].values, available].copy().reset_index(drop=True)
    y_val = val_targets_local['daily_foc'].values

    # Sample weights
    if sample_weights is not None:
        w = sample_weights[train_targets_local['orig_idx'].values]
    else:
        w = None

    # XGBoost
    xgb = XGBRegressor(
        n_estimators=1000, max_depth=7, learning_rate=0.025,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.5, reg_lambda=2.0, min_child_weight=5, gamma=0.1,
        random_state=42, n_jobs=-1,
    )
    if w is not None:
        xgb.fit(X_train, y_train, sample_weight=w, verbose=False)
    else:
        xgb.fit(X_train, y_train, verbose=False)

    # LightGBM
    lgbm = LGBMRegressor(
        n_estimators=1000, max_depth=7, learning_rate=0.025,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.5, reg_lambda=2.0, min_child_samples=10,
        random_state=42, n_jobs=-1, verbose=-1,
    )
    if w is not None:
        lgbm.fit(X_train, y_train, sample_weight=w)
    else:
        lgbm.fit(X_train, y_train)

    # Ensemble
    y_pred = 0.7 * xgb.predict(X_val) + 0.3 * lgbm.predict(X_val)
    y_pred = np.maximum(y_pred, 0)

    mae = mean_absolute_error(y_val, y_pred)
    rmse = np.sqrt(mean_squared_error(y_val, y_pred))
    r2 = r2_score(y_val, y_pred)
    within_5 = (np.abs(y_val - y_pred) <= 5).sum() / len(y_val) * 100
    within_10 = (np.abs(y_val - y_pred) <= 10).sum() / len(y_val) * 100
    high_mask = y_val > 30
    mape_high = np.mean(np.abs(y_val[high_mask] - y_pred[high_mask]) / y_val[high_mask]) * 100 if high_mask.sum() > 0 else 0

    return {
        'Experiment': exp_name,
        'Train_size': len(y_train),
        'Val_size': len(y_val),
        'Features': len(available),
        'MAE': mae, 'RMSE': rmse, 'R2': r2,
        'MAPE_high': mape_high, 'Within5': within_5, 'Within10': within_10,
    }

results = []

# --- 1. 基線: S1-12 穩態, BASE features ---
r = train_and_evaluate(train_strict, val_strict_eval, BASE, exp_name="1: S1-12 穩態 + BASE")
if r: results.append(r); print(f"\n  {r['Experiment']}: MAE={r['MAE']:.3f}, ≤10MT={r['Within10']:.1f}%")

# --- 2. S1-12 穩態, ENHANCED features ---
r = train_and_evaluate(train_strict, val_strict_eval, ENHANCED, exp_name="2: S1-12 穩態 + ENHANCED")
if r: results.append(r); print(f"  {r['Experiment']}: MAE={r['MAE']:.3f}, ≤10MT={r['Within10']:.1f}%")

# --- 3. S1-12+S21-23 穩態 合併訓練, BASE (用 5-fold CV 評估) ---
# 這裡不能用 val_strict 因為已經在 train 裡了
# 改用 KFold CV
print("\n  3: 合併訓練 (S1-12 + S21-23 穩態) — 用 CV 評估")
combined_targets = compute_targets(combined_strict)
available_base = [f for f in BASE if f in combined_strict.columns]
X_combined = combined_strict.loc[combined_targets['orig_idx'].values, available_base].copy().reset_index(drop=True)
y_combined = combined_targets['daily_foc'].values

kf = KFold(n_splits=5, shuffle=True, random_state=42)
cv_maes = []
for tr_idx, va_idx in kf.split(X_combined):
    xgb_cv = XGBRegressor(n_estimators=800, max_depth=7, learning_rate=0.03,
                          subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                          reg_lambda=2.0, min_child_weight=5, gamma=0.1,
                          random_state=42, n_jobs=-1)
    xgb_cv.fit(X_combined.iloc[tr_idx], y_combined[tr_idx], verbose=False)
    lgbm_cv = LGBMRegressor(n_estimators=800, max_depth=7, learning_rate=0.03,
                            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                            reg_lambda=2.0, min_child_samples=10,
                            random_state=42, n_jobs=-1, verbose=-1)
    lgbm_cv.fit(X_combined.iloc[tr_idx], y_combined[tr_idx])
    pred = 0.7 * xgb_cv.predict(X_combined.iloc[va_idx]) + 0.3 * lgbm_cv.predict(X_combined.iloc[va_idx])
    cv_maes.append(mean_absolute_error(y_combined[va_idx], pred))
print(f"    CV MAE: {np.mean(cv_maes):.3f} ± {np.std(cv_maes):.3f}")
results.append({'Experiment': '3: 合併訓練 CV (BASE)', 'Train_size': len(y_combined),
                'Val_size': len(y_combined)//5, 'Features': len(available_base),
                'MAE': np.mean(cv_maes), 'RMSE': 0, 'R2': 0, 'MAPE_high': 0,
                'Within5': 0, 'Within10': 0})

# --- 4. 合併 + ENHANCED CV ---
print("  4: 合併訓練 + ENHANCED — CV")
available_enh = [f for f in ENHANCED if f in combined_strict.columns]
X_comb_enh = combined_strict.loc[combined_targets['orig_idx'].values, available_enh].copy().reset_index(drop=True)
cv_maes_enh = []
for tr_idx, va_idx in kf.split(X_comb_enh):
    xgb_cv = XGBRegressor(n_estimators=800, max_depth=7, learning_rate=0.03,
                          subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                          reg_lambda=2.0, min_child_weight=5, gamma=0.1,
                          random_state=42, n_jobs=-1)
    xgb_cv.fit(X_comb_enh.iloc[tr_idx], y_combined[tr_idx], verbose=False)
    lgbm_cv = LGBMRegressor(n_estimators=800, max_depth=7, learning_rate=0.03,
                            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                            reg_lambda=2.0, min_child_samples=10,
                            random_state=42, n_jobs=-1, verbose=-1)
    lgbm_cv.fit(X_comb_enh.iloc[tr_idx], y_combined[tr_idx])
    pred = 0.7 * xgb_cv.predict(X_comb_enh.iloc[va_idx]) + 0.3 * lgbm_cv.predict(X_comb_enh.iloc[va_idx])
    cv_maes_enh.append(mean_absolute_error(y_combined[va_idx], pred))
print(f"    CV MAE: {np.mean(cv_maes_enh):.3f} ± {np.std(cv_maes_enh):.3f}")
results.append({'Experiment': '4: 合併訓練 CV (ENHANCED)', 'Train_size': len(y_combined),
                'Val_size': len(y_combined)//5, 'Features': len(available_enh),
                'MAE': np.mean(cv_maes_enh), 'RMSE': 0, 'R2': 0, 'MAPE_high': 0,
                'Within5': 0, 'Within10': 0})

# --- 5. S1-12 全部 + sample weighting, BASE ---
print("\n  5: S1-12 全部 + sample weighting")
train_all_feat = add_features(train_all)
sw = np.where(
    (train_all_feat['WIND_SCALE'] <= 4) & (train_all_feat['HOURS_FULL_SPEED'] >= 22),
    1.0, 0.3
)
r = train_and_evaluate(train_all_feat, val_strict_eval, BASE, sample_weights=sw,
                       exp_name="5: S1-12 全部 + weight + BASE")
if r: results.append(r); print(f"    MAE={r['MAE']:.3f}, ≤10MT={r['Within10']:.1f}%")

# --- 6. S1-12 全部 + sample weighting, ENHANCED ---
r = train_and_evaluate(train_all_feat, val_strict_eval, ENHANCED, sample_weights=sw,
                       exp_name="6: S1-12 全部 + weight + ENHANCED")
if r: results.append(r); print(f"    MAE={r['MAE']:.3f}, ≤10MT={r['Within10']:.1f}%")

# --- 7. 全部 (S1-12+S21-23) + sample weighting, ENHANCED ---
print("\n  7: 全部 + weight + ENHANCED")
combined_all_feat = add_features(combined_all)
sw_all = np.where(
    (combined_all_feat['WIND_SCALE'] <= 4) & (combined_all_feat['HOURS_FULL_SPEED'] >= 22),
    1.0, 0.3
)
# 這裡不能用 val_strict_eval（已在 train 裡），用 CV
combined_all_targets = compute_targets(combined_all_feat)
available_enh_all = [f for f in ENHANCED if f in combined_all_feat.columns]
X_all_enh = combined_all_feat.loc[combined_all_targets['orig_idx'].values, available_enh_all].copy().reset_index(drop=True)
y_all_enh = combined_all_targets['daily_foc'].values
sw_all_targets = sw_all[combined_all_targets['orig_idx'].values]

cv_maes_7 = []
for tr_idx, va_idx in kf.split(X_all_enh):
    xgb_cv = XGBRegressor(n_estimators=800, max_depth=7, learning_rate=0.03,
                          subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                          reg_lambda=2.0, min_child_weight=5, gamma=0.1,
                          random_state=42, n_jobs=-1)
    xgb_cv.fit(X_all_enh.iloc[tr_idx], y_all_enh[tr_idx], sample_weight=sw_all_targets[tr_idx], verbose=False)
    lgbm_cv = LGBMRegressor(n_estimators=800, max_depth=7, learning_rate=0.03,
                            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                            reg_lambda=2.0, min_child_samples=10,
                            random_state=42, n_jobs=-1, verbose=-1)
    lgbm_cv.fit(X_all_enh.iloc[tr_idx], y_all_enh[tr_idx], sample_weight=sw_all_targets[tr_idx])
    pred = 0.7 * xgb_cv.predict(X_all_enh.iloc[va_idx]) + 0.3 * lgbm_cv.predict(X_all_enh.iloc[va_idx])
    cv_maes_7.append(mean_absolute_error(y_all_enh[va_idx], pred))
print(f"    CV MAE: {np.mean(cv_maes_7):.3f} ± {np.std(cv_maes_7):.3f}")
results.append({'Experiment': '7: 全部 + weight + ENHANCED CV', 'Train_size': len(y_all_enh),
                'Val_size': len(y_all_enh)//5, 'Features': len(available_enh_all),
                'MAE': np.mean(cv_maes_7), 'RMSE': 0, 'R2': 0, 'MAPE_high': 0,
                'Within5': 0, 'Within10': 0})

# --- 8. 合併穩態 + 用全量重新訓練, 對 test 做 event 內平滑 ---
print("\n  8: 合併穩態 + ENHANCED + 事件內平滑")
# 先訓練 (用合併穩態全量)
X_final = combined_strict.loc[combined_targets['orig_idx'].values, available_enh].copy().reset_index(drop=True)
y_final = combined_targets['daily_foc'].values

xgb_final = XGBRegressor(n_estimators=1000, max_depth=7, learning_rate=0.025,
                         subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                         reg_lambda=2.0, min_child_weight=5, gamma=0.1,
                         random_state=42, n_jobs=-1)
xgb_final.fit(X_final, y_final, verbose=False)
lgbm_final = LGBMRegressor(n_estimators=1000, max_depth=7, learning_rate=0.025,
                           subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                           reg_lambda=2.0, min_child_samples=10,
                           random_state=42, n_jobs=-1, verbose=-1)
lgbm_final.fit(X_final, y_final)

# 預測 test 的 102 筆
test_feat = add_features(test_df)
predictions = []
for idx in test_feat.index:
    for col in target_cols:
        val = str(test_feat.loc[idx, col])
        if val == 'PREDICT':
            ship_id = test_feat.loc[idx, 'ship_id']
            day = test_feat.loc[idx, 'NOON_UTC']
            hours_fs = test_feat.loc[idx, 'HOURS_FULL_SPEED']

            X_pred = test_feat.loc[[idx], available_enh].copy().reset_index(drop=True)
            pred_raw = 0.7 * xgb_final.predict(X_pred)[0] + 0.3 * lgbm_final.predict(X_pred)[0]
            daily_foc = max(pred_raw, 0)

            # 反推原始值
            fuel_lcv = LCV[col]
            if pd.notna(hours_fs) and hours_fs > 0:
                predicted_value = daily_foc * (VLSFO_LCV / fuel_lcv) * hours_fs / 24
            else:
                predicted_value = daily_foc * (VLSFO_LCV / fuel_lcv)

            predictions.append({
                'ship_id': ship_id, 'day': day, 'fuel_type': col,
                'predicted_value': round(max(predicted_value, 0), 2),
                'daily_foc': round(daily_foc, 2),
            })
            break

pred_df = pd.DataFrame(predictions)

# 事件內平滑 (同船連續日期的預測取 3 點移動平均)
print("  事件內平滑...")
pred_df_smoothed = pred_df.copy()
for ship in pred_df['ship_id'].unique():
    mask = pred_df_smoothed['ship_id'] == ship
    ship_pred = pred_df_smoothed[mask].sort_values('day')
    # 找連續事件 (間隔 < 15 天為同一事件)
    days = ship_pred['day'].values
    event_breaks = np.where(np.diff(days) > 15)[0] + 1
    events = np.split(np.arange(len(ship_pred)), event_breaks)

    for event_indices in events:
        if len(event_indices) >= 3:
            event_rows = ship_pred.iloc[event_indices]
            foc_values = event_rows['daily_foc'].values
            # 3-point moving average
            smoothed = np.convolve(foc_values, np.ones(3)/3, mode='same')
            # 邊界保留原值
            smoothed[0] = foc_values[0]
            smoothed[-1] = foc_values[-1]

            for i, ev_idx in enumerate(event_indices):
                orig_idx = ship_pred.index[ev_idx]
                hours_fs = pred_df_smoothed.loc[orig_idx, 'day']  # placeholder
                fuel_col = pred_df_smoothed.loc[orig_idx, 'fuel_type']
                fuel_lcv = LCV[fuel_col]
                hours_fs_val = test_feat.loc[test_feat['NOON_UTC'] == pred_df_smoothed.loc[orig_idx, 'day']]['HOURS_FULL_SPEED']
                h = hours_fs_val.values[0] if len(hours_fs_val) > 0 else 24
                pred_df_smoothed.loc[orig_idx, 'daily_foc'] = round(smoothed[i], 2)
                pred_df_smoothed.loc[orig_idx, 'predicted_value'] = round(
                    max(smoothed[i] * (VLSFO_LCV / fuel_lcv) * h / 24, 0), 2)

# 保存
pred_df[['ship_id', 'day', 'fuel_type', 'predicted_value']].to_csv('submission_v5.csv', index=False)
pred_df_smoothed[['ship_id', 'day', 'fuel_type', 'predicted_value']].to_csv('submission_v5_smoothed.csv', index=False)
print(f"  ✓ submission_v5.csv (未平滑)")
print(f"  ✓ submission_v5_smoothed.csv (事件內平滑)")

# ============================================================================
# 排名
# ============================================================================
print("\n" + "="*80)
print("排名")
print("="*80)

results_df = pd.DataFrame(results).sort_values('MAE')
print(f"\n{'排名':<4} {'實驗':<45} {'Train':<7} {'MAE':<7} {'R²':<8} {'≤5MT%':<7} {'≤10MT%':<7}")
print("-" * 85)
for i, row in enumerate(results_df.itertuples(), 1):
    r2_str = f"{row.R2:.4f}" if row.R2 > 0 else "CV"
    w5 = f"{row.Within5:.1f}" if row.Within5 > 0 else "—"
    w10 = f"{row.Within10:.1f}" if row.Within10 > 0 else "—"
    star = ' ⭐' if i == 1 else ''
    print(f"{i:<4} {row.Experiment:<45} {row.Train_size:<7} {row.MAE:<7.3f} {r2_str:<8} {w5:<7} {w10:<7}{star}")

best = results_df.iloc[0]
print(f"\n🏆 最佳: {best['Experiment']} (MAE={best['MAE']:.3f})")

print(f"\n提交統計:")
print(f"  v5 (未平滑): 平均={pred_df['predicted_value'].mean():.2f}, 範圍={pred_df['predicted_value'].min():.2f}~{pred_df['predicted_value'].max():.2f}")
print(f"  v5 (平滑):   平均={pred_df_smoothed['predicted_value'].mean():.2f}, 範圍={pred_df_smoothed['predicted_value'].min():.2f}~{pred_df_smoothed['predicted_value'].max():.2f}")

results_df.to_csv('experiment_final_results.csv', index=False)
print(f"\n✓ experiment_final_results.csv")
print("="*80 + "\n")
