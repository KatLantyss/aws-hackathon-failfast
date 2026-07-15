"""
XGBoost + LightGBM Ensemble 油耗預測模型 v3
優化：
1. 全速 ≥22hr + 風力 ≤4 級篩選（完全對齊 PREDICT 條件）
2. W1/W2 船型分群模型
3. XGBoost + LightGBM 加權平均 ensemble
"""

import pandas as pd
import numpy as np
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold
import warnings
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
warnings.filterwarnings('ignore')

try:
    from lightgbm import LGBMRegressor
    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False
    print("  [WARN] LightGBM not installed, using XGBoost only")

print("\n" + "="*80)
print("v3 — 分群 Ensemble (XGBoost + LightGBM)")
print("="*80)

# ============================================================================
# 1. 加載 & 篩選
# ============================================================================
print("\n[1/7] 加載數據...")
train_df = pd.read_csv('data_train_with_maintenance.csv', low_memory=False)
validate_df = pd.read_csv('data_validate_with_maintenance.csv', low_memory=False)
test_df = pd.read_csv('data_test_with_maintenance.csv', low_memory=False)

# 數值轉換
for col in ['WIND_SCALE', 'HOURS_FULL_SPEED']:
    train_df[col] = pd.to_numeric(train_df[col], errors='coerce')
    validate_df[col] = pd.to_numeric(validate_df[col], errors='coerce')
    test_df[col] = pd.to_numeric(test_df[col], errors='coerce')

# 篩選：風力 ≤4 AND 全速 ≥22hr（完全對齊 PREDICT 條件）
print("\n[2/7] 篩選穩態條件 (風力≤4 + 全速≥22hr)...")
train_before = len(train_df)
train_df = train_df[(train_df['WIND_SCALE'] <= 4) & (train_df['HOURS_FULL_SPEED'] >= 22)].reset_index(drop=True)
print(f"  Train: {train_before} → {len(train_df)} (移除 {train_before - len(train_df)})")

val_before = len(validate_df)
validate_df_strict = validate_df[(validate_df['WIND_SCALE'] <= 4) & (validate_df['HOURS_FULL_SPEED'] >= 22)].reset_index(drop=True)
print(f"  Validate (strict): {val_before} → {len(validate_df_strict)}")

# 也保留寬鬆版驗證 (只篩風力)
validate_df_loose = validate_df[validate_df['WIND_SCALE'] <= 4].reset_index(drop=True)
print(f"  Validate (loose, 風力≤4): {len(validate_df_loose)}")

# ============================================================================
# 3. 特徵定義 (組合 F: 最佳)
# ============================================================================
print("\n[3/7] 特徵定義 (組合 F)...")

target_cols = ['ME_FULLSPEED_CONSUMP_HSHFO', 'ME_FULLSPEED_CONSUMP_VLSFO',
               'ME_FULLSPEED_CONSUMP_ULSFO', 'ME_FULLSPEED_CONSUMP_LSMGO',
               'ME_FULLSPEED_CONSUMP_BIO_HSFO']
fuel_heat_values = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
    'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
    'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}
fuel_type_map = {col: i for i, col in enumerate(target_cols)}

# 組合 F: CORE + HULL + SPEED + WEATHER + MAINT_SLIM
features = [
    # CORE
    'SEA_SPEED_DISTANCE', 'TOTAL_DISTANCE', 'ME_AVG_RPM', 'PROPELLER_SPEED',
    'HOURS_FULL_SPEED', 'HOURS_TOTAL',
    # HULL
    'FORE_DRAFT', 'AFTER_DRAFT', 'MID_DRAFT', 'DISPLACEMENT', 'CARGO_ON_BOARD',
    # SPEED
    'AVG_SPEED', 'SPEED_THROUGH_WATER', 'DIFF_STW_SOG_SLIP', 'FULL_SPD_STW_SLIP',
    # WEATHER
    'WIND_SCALE', 'WIND_SPEED', 'WIND_DIRECTION', 'SEA_HEIGHT', 'SEA_DIRECTION',
    'SWELL_HEIGHT', 'SWELL_DIRECTION', 'SEA_WATER_TEMP', 'WATER_DEPTH',
    # MAINT_SLIM
    'DAYS_SINCE_LAST_MAINT', 'LAST_MAINT_TYPE',
]
available_features = [f for f in features if f in train_df.columns]
print(f"  可用特徵: {len(available_features)}")

# ============================================================================
# 4. 準備數據
# ============================================================================
print("\n[4/7] 準備訓練數據...")

def prepare_target(df):
    rows = []
    for idx in df.index:
        for col in target_cols:
            val = df.loc[idx, col]
            try:
                v = float(val)
                if not np.isnan(v) and v > 0:
                    rows.append({'orig_idx': idx, 'fuel_type': col,
                                 'consumption_mt': v, 'heat_value': fuel_heat_values[col]})
                    break
            except (ValueError, TypeError):
                continue
    return pd.DataFrame(rows)

def build_X(df, targets, features):
    X = df.loc[targets['orig_idx'].values, features].copy()
    for col in features:
        X[col] = pd.to_numeric(X[col], errors='coerce')
    X['FUEL_TYPE_CODE'] = targets['fuel_type'].map(fuel_type_map).values
    X['FUEL_HEAT_VALUE'] = targets['heat_value'].values
    return X

# W1 型: S1-S8, S21
# W2 型: S9-S12, S22-S23
W1_SHIPS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S21']
W2_SHIPS = ['S9', 'S10', 'S11', 'S12', 'S22', 'S23']

def get_ship_type(ship_id):
    return 'W1' if ship_id in W1_SHIPS else 'W2'

# ============================================================================
# 5. 分群訓練
# ============================================================================
print("\n[5/7] 分群訓練 (W1 + W2)...")

feature_cols_final = available_features + ['FUEL_TYPE_CODE', 'FUEL_HEAT_VALUE']
models = {}  # {'W1_xgb': model, 'W1_lgbm': model, 'W2_xgb': model, ...}

for ship_type, ship_list in [('W1', W1_SHIPS), ('W2', W2_SHIPS)]:
    print(f"\n  === {ship_type} 型 ({ship_list}) ===")

    # 訓練船
    train_ships = [s for s in ship_list if s not in ['S21', 'S22', 'S23']]
    type_train = train_df[train_df['ship_id'].isin(train_ships)].reset_index(drop=True)
    type_targets = prepare_target(type_train)

    if len(type_targets) == 0:
        print(f"    無有效訓練數據, 跳過")
        continue

    X_train = build_X(type_train, type_targets, available_features)
    y_train = type_targets['consumption_mt'].values
    valid_mask = ~np.isnan(y_train)
    X_clean = X_train[valid_mask].reset_index(drop=True)
    y_clean = y_train[valid_mask]
    print(f"    訓練樣本: {len(y_clean)}")

    # XGBoost
    xgb_model = XGBRegressor(
        n_estimators=1000, max_depth=7, learning_rate=0.025,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.5, reg_lambda=2.0, min_child_weight=5, gamma=0.1,
        random_state=42, n_jobs=-1,
    )
    xgb_model.fit(X_clean, y_clean, verbose=False)
    models[f'{ship_type}_xgb'] = xgb_model

    # CV score for XGBoost
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    cv_maes = []
    for train_idx, val_idx in kf.split(X_clean):
        m = XGBRegressor(n_estimators=800, max_depth=7, learning_rate=0.03,
                         subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                         reg_lambda=2.0, min_child_weight=5, gamma=0.1,
                         random_state=42, n_jobs=-1)
        m.fit(X_clean.iloc[train_idx], y_clean[train_idx], verbose=False)
        pred = m.predict(X_clean.iloc[val_idx])
        cv_maes.append(mean_absolute_error(y_clean[val_idx], pred))
    print(f"    XGBoost CV MAE: {np.mean(cv_maes):.3f}")

    # LightGBM
    if HAS_LGBM:
        lgbm_model = LGBMRegressor(
            n_estimators=1000, max_depth=7, learning_rate=0.025,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.5, reg_lambda=2.0, min_child_samples=10,
            random_state=42, n_jobs=-1, verbose=-1,
        )
        lgbm_model.fit(X_clean, y_clean)
        models[f'{ship_type}_lgbm'] = lgbm_model

        cv_maes_lgbm = []
        for train_idx, val_idx in kf.split(X_clean):
            m = LGBMRegressor(n_estimators=800, max_depth=7, learning_rate=0.03,
                              subsample=0.8, colsample_bytree=0.8, reg_alpha=0.5,
                              reg_lambda=2.0, min_child_samples=10,
                              random_state=42, n_jobs=-1, verbose=-1)
            m.fit(X_clean.iloc[train_idx], y_clean[train_idx])
            pred = m.predict(X_clean.iloc[val_idx])
            cv_maes_lgbm.append(mean_absolute_error(y_clean[val_idx], pred))
        print(f"    LightGBM CV MAE: {np.mean(cv_maes_lgbm):.3f}")

# ============================================================================
# 6. 驗證
# ============================================================================
print("\n[6/7] 驗證集評估...")

def predict_ensemble(df, targets, models, features):
    """用分群 ensemble 預測"""
    X = build_X(df, targets, features)
    predictions = np.zeros(len(X))

    for i, row_idx in enumerate(targets['orig_idx'].values):
        ship_id = df.loc[row_idx, 'ship_id']
        ship_type = get_ship_type(ship_id)

        x_row = X.iloc[[i]]

        # XGBoost prediction
        xgb_key = f'{ship_type}_xgb'
        xgb_pred = models[xgb_key].predict(x_row)[0] if xgb_key in models else 0

        # LightGBM prediction
        lgbm_key = f'{ship_type}_lgbm'
        if lgbm_key in models:
            lgbm_pred = models[lgbm_key].predict(x_row)[0]
            # Ensemble: 0.5 XGBoost + 0.5 LightGBM
            predictions[i] = 0.5 * xgb_pred + 0.5 * lgbm_pred
        else:
            predictions[i] = xgb_pred

    return predictions

# Strict validation (風力≤4 + 全速≥22hr)
val_targets_strict = prepare_target(validate_df_strict)
if len(val_targets_strict) > 0:
    y_val = val_targets_strict['consumption_mt'].values
    valid_mask = ~np.isnan(y_val)
    val_targets_valid = val_targets_strict[valid_mask].reset_index(drop=True)
    validate_df_strict_valid = validate_df_strict.copy()

    y_val_clean = y_val[valid_mask]
    y_pred = predict_ensemble(validate_df_strict, val_targets_valid, models, available_features)

    mae = mean_absolute_error(y_val_clean, y_pred)
    rmse = np.sqrt(mean_squared_error(y_val_clean, y_pred))
    r2 = r2_score(y_val_clean, y_pred)
    high = y_val_clean > 10
    mape = np.mean(np.abs(y_val_clean[high] - y_pred[high]) / y_val_clean[high]) * 100

    within_5 = (np.abs(y_val_clean - y_pred) <= 5).sum() / len(y_val_clean) * 100
    within_10 = (np.abs(y_val_clean - y_pred) <= 10).sum() / len(y_val_clean) * 100

    print(f"\n  ┌─────────────────────────────────────────────┐")
    print(f"  │  驗證集 (strict: 風力≤4 + 全速≥22hr)          │")
    print(f"  │  樣本數: {len(y_val_clean):<35}│")
    print(f"  ├─────────────────────────────────────────────┤")
    print(f"  │  MAE:   {mae:.3f} MT/day                       │")
    print(f"  │  RMSE:  {rmse:.3f} MT/day                       │")
    print(f"  │  R²:    {r2:.4f}                            │")
    print(f"  │  MAPE:  {mape:.2f}%                            │")
    print(f"  │  ≤5 MT:  {within_5:.1f}%                           │")
    print(f"  │  ≤10 MT: {within_10:.1f}%                           │")
    print(f"  └─────────────────────────────────────────────┘")

    # 按船舶
    print(f"\n  按船舶:")
    for ship in sorted(validate_df_strict['ship_id'].unique()):
        ship_mask = validate_df_strict.loc[val_targets_valid['orig_idx'].values, 'ship_id'].values == ship
        if ship_mask.sum() > 0:
            s_mae = mean_absolute_error(y_val_clean[ship_mask], y_pred[ship_mask])
            s_r2 = r2_score(y_val_clean[ship_mask], y_pred[ship_mask]) if ship_mask.sum() > 1 else 0
            print(f"    {ship}: {ship_mask.sum()} 行, MAE={s_mae:.3f}, R²={s_r2:.4f}")

# Loose validation
val_targets_loose = prepare_target(validate_df_loose)
if len(val_targets_loose) > 0:
    y_val_l = val_targets_loose['consumption_mt'].values
    valid_mask_l = ~np.isnan(y_val_l)
    val_targets_loose_valid = val_targets_loose[valid_mask_l].reset_index(drop=True)
    y_val_l_clean = y_val_l[valid_mask_l]
    y_pred_l = predict_ensemble(validate_df_loose, val_targets_loose_valid, models, available_features)
    mae_l = mean_absolute_error(y_val_l_clean, y_pred_l)
    r2_l = r2_score(y_val_l_clean, y_pred_l)
    print(f"\n  Loose 驗證 (風力≤4): {len(y_val_l_clean)} 行, MAE={mae_l:.3f}, R²={r2_l:.4f}")

# ============================================================================
# 7. 預測提交
# ============================================================================
print("\n[7/7] 預測 102 筆...")

predictions = []
for idx in test_df.index:
    for col in target_cols:
        val = str(test_df.loc[idx, col])
        if val == 'PREDICT':
            ship_id = test_df.loc[idx, 'ship_id']
            day = test_df.loc[idx, 'NOON_UTC']
            ship_type = get_ship_type(ship_id)

            X_pred = test_df.loc[[idx], available_features].copy()
            for f in available_features:
                X_pred[f] = pd.to_numeric(X_pred[f], errors='coerce')
            X_pred['FUEL_TYPE_CODE'] = fuel_type_map[col]
            X_pred['FUEL_HEAT_VALUE'] = fuel_heat_values[col]

            # Ensemble prediction
            xgb_key = f'{ship_type}_xgb'
            xgb_pred = models[xgb_key].predict(X_pred)[0] if xgb_key in models else 0

            lgbm_key = f'{ship_type}_lgbm'
            if lgbm_key in models:
                lgbm_pred = models[lgbm_key].predict(X_pred)[0]
                final_pred = 0.5 * xgb_pred + 0.5 * lgbm_pred
            else:
                final_pred = xgb_pred

            predictions.append({
                'ship_id': ship_id,
                'day': day,
                'fuel_type': col,
                'predicted_value': round(final_pred, 2),
            })
            break

submission = pd.DataFrame(predictions)
submission.to_csv('submission_v3.csv', index=False)

print(f"\n  ✓ submission_v3.csv ({len(predictions)} 筆)")
print(f"  平均: {submission['predicted_value'].mean():.2f} MT/day")
print(f"  範圍: {submission['predicted_value'].min():.2f} ~ {submission['predicted_value'].max():.2f}")
for ship in sorted(submission['ship_id'].unique()):
    s = submission[submission['ship_id'] == ship]
    print(f"    {ship}: {len(s)} 筆, 平均 {s['predicted_value'].mean():.2f} MT/day")

# ============================================================================
# 版本比較
# ============================================================================
print("\n" + "="*80)
print("版本比較")
print("="*80)
print(f"""
  v2 (單一模型, 風力≤4):
    Val MAE:  3.888 MT/day
    Val R²:   0.9608

  v3 (分群 Ensemble, 風力≤4 + 全速≥22hr):
    Val MAE:  {mae:.3f} MT/day
    Val R²:   {r2:.4f}
    Val MAPE: {mape:.2f}%
    ≤5 MT 準確率: {within_5:.1f}%
    ≤10 MT 準確率: {within_10:.1f}%
""")
print("="*80 + "\n")
