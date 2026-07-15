"""
進階優化實驗 — 找最佳組合
測試：
1. 目標轉換 (log, 殘差)
2. 新特徵 (Speed Loss, 同船歷史均值, 季節性, 航次)
3. 三模型 ensemble (XGB + LGBM + CatBoost/Ridge)
4. Target Encoding
"""

import pandas as pd
import numpy as np
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
import warnings
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
warnings.filterwarnings('ignore')

print("\n" + "="*80)
print("進階優化實驗")
print("="*80)

# ============================================================================
# 加載 & 基礎準備
# ============================================================================
train_df = pd.read_csv('data_train_with_maintenance.csv', low_memory=False)
validate_df = pd.read_csv('data_validate_with_maintenance.csv', low_memory=False)

# 也載入 speed_loss_results
try:
    sl_df = pd.read_csv('speed_loss_results.csv')
    HAS_SL = True
    print("  ✓ speed_loss_results.csv 已載入")
except:
    HAS_SL = False
    print("  ✗ speed_loss_results.csv 不存在")

# 數值轉換
num_cols = ['WIND_SCALE', 'HOURS_FULL_SPEED', 'ME_AVG_RPM', 'PROPELLER_SPEED',
            'SPEED_THROUGH_WATER', 'AVG_SPEED', 'DISPLACEMENT', 'NOON_UTC',
            'FORE_DRAFT', 'AFTER_DRAFT', 'MID_DRAFT', 'CARGO_ON_BOARD',
            'WIND_SPEED', 'WIND_DIRECTION', 'SEA_HEIGHT', 'SEA_DIRECTION',
            'SWELL_HEIGHT', 'SWELL_DIRECTION', 'SEA_WATER_TEMP', 'WATER_DEPTH',
            'TOTAL_DISTANCE', 'SEA_SPEED_DISTANCE', 'DIFF_STW_SOG_SLIP',
            'FULL_SPD_STW_SLIP', 'HOURS_TOTAL', 'DAYS_SINCE_LAST_MAINT', 'LAST_MAINT_TYPE']
for col in num_cols:
    if col in train_df.columns:
        train_df[col] = pd.to_numeric(train_df[col], errors='coerce')
    if col in validate_df.columns:
        validate_df[col] = pd.to_numeric(validate_df[col], errors='coerce')

# 篩選
train_df = train_df[(train_df['WIND_SCALE'] <= 4) & (train_df['HOURS_FULL_SPEED'] >= 22)].reset_index(drop=True)
validate_df = validate_df[(validate_df['WIND_SCALE'] <= 4) & (validate_df['HOURS_FULL_SPEED'] >= 22)].reset_index(drop=True)

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

train_targets = compute_targets(train_df)
val_targets = compute_targets(validate_df)
print(f"\nTrain: {len(train_targets)}, Validate: {len(val_targets)}")

# ============================================================================
# 計算進階特徵
# ============================================================================
print("\n計算進階特徵...")

W1_SHIPS = ['S1','S2','S3','S4','S5','S6','S7','S8','S21']

def add_advanced_features(df, train_df_full, sl_df=None):
    """加入所有進階特徵"""
    df = df.copy()

    # --- 1. 物理基線 (Admiralty) ---
    rpm = df['ME_AVG_RPM'].clip(lower=1)
    disp = df['DISPLACEMENT'].clip(lower=1)
    C = df['ship_id'].apply(lambda s: 332.0 if s in W1_SHIPS else 315.0)
    df['PHYSICS_FOC'] = C * (rpm / 100)**3 * (disp / 100000)**(2/3)

    # --- 2. Speed Loss 當特徵 ---
    if sl_df is not None and HAS_SL:
        # 合併 speed_loss_pct (by ship_id + NOON_UTC)
        sl_clean = sl_df[['ship_id', 'NOON_UTC', 'speed_loss_pct']].copy()
        sl_clean['NOON_UTC'] = pd.to_numeric(sl_clean['NOON_UTC'], errors='coerce')
        sl_clean['speed_loss_pct'] = pd.to_numeric(sl_clean['speed_loss_pct'], errors='coerce')
        # 過濾極端值
        sl_clean = sl_clean[(sl_clean['speed_loss_pct'] > -30) & (sl_clean['speed_loss_pct'] < 50)]
        df = df.merge(sl_clean, on=['ship_id', 'NOON_UTC'], how='left')
        df['speed_loss_pct'] = df['speed_loss_pct'].fillna(0)
    else:
        df['speed_loss_pct'] = 0

    # --- 3. 同船歷史均值 (Target Encoding 概念) ---
    # 用訓練集計算每艘船的平均 Daily FOC
    ship_means = train_df_full.groupby('ship_id').apply(
        lambda g: compute_targets(g)['daily_foc'].mean() if len(compute_targets(g)) > 0 else 60.0
    )
    df['SHIP_MEAN_FOC'] = df['ship_id'].map(ship_means).fillna(60.0)

    # --- 4. 同船近期均值 (rolling, 用 NOON_UTC 近似) ---
    # 該船在當前日期前 30/60 天的平均 RPM (代理近期狀態)
    df['SHIP_RECENT_RPM'] = df.groupby('ship_id')['ME_AVG_RPM'].transform(
        lambda x: x.rolling(window=10, min_periods=1).mean()
    )

    # --- 5. 季節性 ---
    df['SEASON'] = (df['NOON_UTC'] % 365) / 365  # 0~1 循環
    df['SEASON_SIN'] = np.sin(2 * np.pi * df['SEASON'])
    df['SEASON_COS'] = np.cos(2 * np.pi * df['SEASON'])

    # --- 6. 退化平方根 ---
    df['DAYS_SINCE_MAINT_SQRT'] = np.sqrt(df['DAYS_SINCE_LAST_MAINT'].clip(lower=0))

    # --- 7. 殘差目標 (用於殘差模型) ---
    df['RESIDUAL_TARGET'] = None  # 稍後在訓練時計算

    return df

# 計算同船平均 (用原始完整訓練集)
train_df_for_mean = pd.read_csv('data_train_with_maintenance.csv', low_memory=False)
for col in num_cols:
    if col in train_df_for_mean.columns:
        train_df_for_mean[col] = pd.to_numeric(train_df_for_mean[col], errors='coerce')
train_df_for_mean = train_df_for_mean[(train_df_for_mean['WIND_SCALE'] <= 4) & (train_df_for_mean['HOURS_FULL_SPEED'] >= 22)].reset_index(drop=True)

train_df = add_advanced_features(train_df, train_df_for_mean, sl_df)
validate_df = add_advanced_features(validate_df, train_df_for_mean, sl_df)

# 重新計算 targets (因為 merge 可能改了 index)
train_targets = compute_targets(train_df)
val_targets = compute_targets(validate_df)
print(f"  重新計算後 - Train: {len(train_targets)}, Validate: {len(val_targets)}")

# ============================================================================
# 定義實驗
# ============================================================================

BASE_FEATURES = [
    'SEA_SPEED_DISTANCE', 'TOTAL_DISTANCE', 'ME_AVG_RPM', 'PROPELLER_SPEED',
    'HOURS_TOTAL', 'FORE_DRAFT', 'AFTER_DRAFT', 'MID_DRAFT', 'DISPLACEMENT',
    'CARGO_ON_BOARD', 'AVG_SPEED', 'SPEED_THROUGH_WATER', 'DIFF_STW_SOG_SLIP',
    'FULL_SPD_STW_SLIP', 'WIND_SCALE', 'WIND_SPEED', 'WIND_DIRECTION',
    'SEA_HEIGHT', 'SEA_DIRECTION', 'SWELL_HEIGHT', 'SWELL_DIRECTION',
    'SEA_WATER_TEMP', 'WATER_DEPTH', 'DAYS_SINCE_LAST_MAINT', 'LAST_MAINT_TYPE',
]

NEW_FEATURES = {
    'speed_loss': ['speed_loss_pct'],
    'ship_mean': ['SHIP_MEAN_FOC'],
    'ship_recent': ['SHIP_RECENT_RPM'],
    'season': ['SEASON_SIN', 'SEASON_COS'],
    'physics': ['PHYSICS_FOC'],
    'degradation': ['DAYS_SINCE_MAINT_SQRT'],
}

def build_X_y(df, targets, features):
    X = df.loc[targets['orig_idx'].values, features].copy().reset_index(drop=True)
    for col in features:
        X[col] = pd.to_numeric(X[col], errors='coerce')
    y = targets['daily_foc'].values
    return X, y

def run_experiment(X_train, y_train, X_val, y_val, use_log=False, use_residual=False, physics_train=None, physics_val=None):
    """跑一次實驗, 返回 metrics"""

    if use_log:
        y_tr = np.log1p(y_train)
        y_target = y_tr
    elif use_residual and physics_train is not None:
        y_tr = y_train - physics_train
        y_target = y_tr
    else:
        y_target = y_train

    # XGBoost
    xgb = XGBRegressor(
        n_estimators=1000, max_depth=7, learning_rate=0.025,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.5, reg_lambda=2.0, min_child_weight=5, gamma=0.1,
        random_state=42, n_jobs=-1,
    )
    xgb.fit(X_train, y_target, verbose=False)

    # LightGBM
    lgbm = LGBMRegressor(
        n_estimators=1000, max_depth=7, learning_rate=0.025,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.5, reg_lambda=2.0, min_child_samples=10,
        random_state=42, n_jobs=-1, verbose=-1,
    )
    lgbm.fit(X_train, y_target)

    # Ensemble
    p_xgb = xgb.predict(X_val)
    p_lgbm = lgbm.predict(X_val)
    y_pred_raw = 0.7 * p_xgb + 0.3 * p_lgbm

    # 反轉換
    if use_log:
        y_pred = np.expm1(y_pred_raw)
    elif use_residual and physics_val is not None:
        y_pred = physics_val + y_pred_raw
    else:
        y_pred = y_pred_raw

    y_pred = np.maximum(y_pred, 0)

    mae = mean_absolute_error(y_val, y_pred)
    rmse = np.sqrt(mean_squared_error(y_val, y_pred))
    r2 = r2_score(y_val, y_pred)
    within_5 = (np.abs(y_val - y_pred) <= 5).sum() / len(y_val) * 100
    within_10 = (np.abs(y_val - y_pred) <= 10).sum() / len(y_val) * 100
    high_mask = y_val > 30
    mape_high = np.mean(np.abs(y_val[high_mask] - y_pred[high_mask]) / y_val[high_mask]) * 100

    return {'MAE': mae, 'RMSE': rmse, 'R2': r2, 'MAPE_high': mape_high,
            'Within5': within_5, 'Within10': within_10}

# ============================================================================
# 跑實驗
# ============================================================================
print("\n" + "="*80)
print("實驗 (共 18 組)")
print("="*80)

results = []

# --- 實驗 1-6: 逐步加入新特徵 ---
feature_combos = [
    ('A: BASE only', BASE_FEATURES, False, False),
    ('B: + speed_loss', BASE_FEATURES + NEW_FEATURES['speed_loss'], False, False),
    ('C: + ship_mean', BASE_FEATURES + NEW_FEATURES['ship_mean'], False, False),
    ('D: + speed_loss + ship_mean', BASE_FEATURES + NEW_FEATURES['speed_loss'] + NEW_FEATURES['ship_mean'], False, False),
    ('E: + all new features', BASE_FEATURES + sum(NEW_FEATURES.values(), []), False, False),
    ('F: + speed_loss + ship_mean + season', BASE_FEATURES + NEW_FEATURES['speed_loss'] + NEW_FEATURES['ship_mean'] + NEW_FEATURES['season'], False, False),
    ('G: + speed_loss + ship_mean + degradation', BASE_FEATURES + NEW_FEATURES['speed_loss'] + NEW_FEATURES['ship_mean'] + NEW_FEATURES['degradation'], False, False),
    ('H: + speed_loss + ship_mean + physics', BASE_FEATURES + NEW_FEATURES['speed_loss'] + NEW_FEATURES['ship_mean'] + NEW_FEATURES['physics'], False, False),
]

# --- 實驗 7-8: 目標轉換 ---
target_combos = [
    ('I: LOG transform (best features)', None, True, False),
    ('J: RESIDUAL (learn deviation from physics)', None, False, True),
]

for exp_name, feat_list, use_log, use_residual in feature_combos:
    available = [f for f in feat_list if f in train_df.columns]
    X_train, y_train_raw = build_X_y(train_df, train_targets, available)
    X_val, y_val_raw = build_X_y(validate_df, val_targets, available)

    metrics = run_experiment(X_train, y_train_raw, X_val, y_val_raw)
    metrics['Experiment'] = exp_name
    metrics['Features'] = len(available)
    results.append(metrics)
    print(f"\n  {exp_name}")
    print(f"    MAE={metrics['MAE']:.3f}, R²={metrics['R2']:.4f}, ≤5MT={metrics['Within5']:.1f}%, ≤10MT={metrics['Within10']:.1f}%")

# 找到目前最佳特徵組合
best_so_far = min(results, key=lambda x: x['MAE'])
best_features_name = best_so_far['Experiment']
# 用最佳特徵跑 log/residual
if 'speed_loss + ship_mean' in best_features_name:
    best_feat_list = BASE_FEATURES + NEW_FEATURES['speed_loss'] + NEW_FEATURES['ship_mean']
else:
    best_feat_list = BASE_FEATURES + NEW_FEATURES['speed_loss'] + NEW_FEATURES['ship_mean']

available_best = [f for f in best_feat_list if f in train_df.columns]

# Log transform
X_train_best, y_train_best = build_X_y(train_df, train_targets, available_best)
X_val_best, y_val_best = build_X_y(validate_df, val_targets, available_best)

metrics_log = run_experiment(X_train_best, y_train_best, X_val_best, y_val_best, use_log=True)
metrics_log['Experiment'] = 'I: LOG transform (D features)'
metrics_log['Features'] = len(available_best)
results.append(metrics_log)
print(f"\n  I: LOG transform (D features)")
print(f"    MAE={metrics_log['MAE']:.3f}, R²={metrics_log['R2']:.4f}, ≤5MT={metrics_log['Within5']:.1f}%, ≤10MT={metrics_log['Within10']:.1f}%")

# Residual model
physics_feat = 'PHYSICS_FOC'
if physics_feat in train_df.columns:
    feat_with_physics = available_best + ['PHYSICS_FOC'] if 'PHYSICS_FOC' not in available_best else available_best
    feat_with_physics = [f for f in feat_with_physics if f in train_df.columns]
    X_train_r, y_train_r = build_X_y(train_df, train_targets, feat_with_physics)
    X_val_r, y_val_r = build_X_y(validate_df, val_targets, feat_with_physics)
    physics_train = train_df.loc[train_targets['orig_idx'].values, 'PHYSICS_FOC'].values
    physics_val = validate_df.loc[val_targets['orig_idx'].values, 'PHYSICS_FOC'].values

    # 填充 NaN (用中位數)
    physics_median = np.nanmedian(physics_train)
    physics_train = np.where(np.isnan(physics_train), physics_median, physics_train)
    physics_val = np.where(np.isnan(physics_val), physics_median, physics_val)

    metrics_res = run_experiment(X_train_r, y_train_r, X_val_r, y_val_r,
                                use_residual=True, physics_train=physics_train, physics_val=physics_val)
    metrics_res['Experiment'] = 'J: RESIDUAL (physics + ML correction)'
    metrics_res['Features'] = len(feat_with_physics)
    results.append(metrics_res)
    print(f"\n  J: RESIDUAL (physics + ML correction)")
    print(f"    MAE={metrics_res['MAE']:.3f}, R²={metrics_res['R2']:.4f}, ≤5MT={metrics_res['Within5']:.1f}%, ≤10MT={metrics_res['Within10']:.1f}%")

# --- 實驗 K: 三模型 Stacking ---
print(f"\n  K: Stacking (XGB + LGBM + Ridge meta-learner)")
X_train_stack, y_train_stack = build_X_y(train_df, train_targets, available_best)
X_val_stack, y_val_stack = build_X_y(validate_df, val_targets, available_best)

# 用 CV 生成 out-of-fold predictions
kf = KFold(n_splits=5, shuffle=True, random_state=42)
oof_xgb = np.zeros(len(X_train_stack))
oof_lgbm = np.zeros(len(X_train_stack))

for tr_idx, va_idx in kf.split(X_train_stack):
    xgb_fold = XGBRegressor(n_estimators=800, max_depth=7, learning_rate=0.03,
                            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                            reg_lambda=2.0, min_child_weight=5, gamma=0.1,
                            random_state=42, n_jobs=-1)
    xgb_fold.fit(X_train_stack.iloc[tr_idx], y_train_stack[tr_idx], verbose=False)
    oof_xgb[va_idx] = xgb_fold.predict(X_train_stack.iloc[va_idx])

    lgbm_fold = LGBMRegressor(n_estimators=800, max_depth=7, learning_rate=0.03,
                              subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                              reg_lambda=2.0, min_child_samples=10,
                              random_state=42, n_jobs=-1, verbose=-1)
    lgbm_fold.fit(X_train_stack.iloc[tr_idx], y_train_stack[tr_idx])
    oof_lgbm[va_idx] = lgbm_fold.predict(X_train_stack.iloc[va_idx])

# Meta-learner
meta_X_train = np.column_stack([oof_xgb, oof_lgbm])
meta_model = Ridge(alpha=1.0)
meta_model.fit(meta_X_train, y_train_stack)

# 驗證
xgb_full = XGBRegressor(n_estimators=1000, max_depth=7, learning_rate=0.025,
                        subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                        reg_lambda=2.0, min_child_weight=5, gamma=0.1,
                        random_state=42, n_jobs=-1)
xgb_full.fit(X_train_stack, y_train_stack, verbose=False)
lgbm_full = LGBMRegressor(n_estimators=1000, max_depth=7, learning_rate=0.025,
                          subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                          reg_lambda=2.0, min_child_samples=10,
                          random_state=42, n_jobs=-1, verbose=-1)
lgbm_full.fit(X_train_stack, y_train_stack)

val_xgb = xgb_full.predict(X_val_stack)
val_lgbm = lgbm_full.predict(X_val_stack)
meta_X_val = np.column_stack([val_xgb, val_lgbm])
y_pred_stack = meta_model.predict(meta_X_val)
y_pred_stack = np.maximum(y_pred_stack, 0)

mae_stack = mean_absolute_error(y_val_stack, y_pred_stack)
r2_stack = r2_score(y_val_stack, y_pred_stack)
within5_stack = (np.abs(y_val_stack - y_pred_stack) <= 5).sum() / len(y_val_stack) * 100
within10_stack = (np.abs(y_val_stack - y_pred_stack) <= 10).sum() / len(y_val_stack) * 100
high_mask = y_val_stack > 30
mape_stack = np.mean(np.abs(y_val_stack[high_mask] - y_pred_stack[high_mask]) / y_val_stack[high_mask]) * 100

results.append({
    'Experiment': 'K: Stacking (Ridge meta)',
    'Features': len(available_best),
    'MAE': mae_stack, 'RMSE': np.sqrt(mean_squared_error(y_val_stack, y_pred_stack)),
    'R2': r2_stack, 'MAPE_high': mape_stack,
    'Within5': within5_stack, 'Within10': within10_stack,
})
print(f"    MAE={mae_stack:.3f}, R²={r2_stack:.4f}, ≤5MT={within5_stack:.1f}%, ≤10MT={within10_stack:.1f}%")
print(f"    Ridge weights: XGB={meta_model.coef_[0]:.3f}, LGBM={meta_model.coef_[1]:.3f}")

# ============================================================================
# 排名
# ============================================================================
print("\n" + "="*80)
print("最終排名 (按 MAE)")
print("="*80)

results_df = pd.DataFrame(results).sort_values('MAE')
print(f"\n{'排名':<4} {'實驗':<45} {'特徵':<5} {'MAE':<7} {'R²':<8} {'MAPE%':<7} {'≤5MT%':<7} {'≤10MT%':<7}")
print("-" * 90)
for i, row in enumerate(results_df.itertuples(), 1):
    star = ' ⭐' if i == 1 else ''
    print(f"{i:<4} {row.Experiment:<45} {row.Features:<5} {row.MAE:<7.3f} {row.R2:<8.4f} {row.MAPE_high:<7.1f} {row.Within5:<7.1f} {row.Within10:<7.1f}{star}")

best = results_df.iloc[0]
base = results_df[results_df['Experiment'].str.startswith('A:')].iloc[0]
print(f"\n🏆 最佳: {best['Experiment']}")
print(f"   MAE: {base['MAE']:.3f} → {best['MAE']:.3f} (改善 {base['MAE']-best['MAE']:.3f} MT/day)")
print(f"   R²:  {base['R2']:.4f} → {best['R2']:.4f}")
print(f"   ≤10MT: {base['Within10']:.1f}% → {best['Within10']:.1f}%")

results_df.to_csv('experiment_advanced_results.csv', index=False)
print(f"\n✓ 結果已保存至 experiment_advanced_results.csv")
print("="*80 + "\n")
