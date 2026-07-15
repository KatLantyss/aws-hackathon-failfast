"""
XGBoost 油耗預測模型
- 使用 data_train_with_maintenance.csv 訓練
- 使用 data_validate_with_maintenance.csv 驗證
- 對 data_test_with_maintenance.csv 做 102 筆 PREDICT 預測
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

print("\n" + "="*80)
print("XGBoost 油耗預測模型 - 訓練與驗證")
print("="*80)

# ============================================================================
# 1. 加載數據
# ============================================================================
print("\n[1/6] 加載數據...")
train_df = pd.read_csv('data_train_with_maintenance.csv', low_memory=False)
validate_df = pd.read_csv('data_validate_with_maintenance.csv', low_memory=False)
test_df = pd.read_csv('data_test_with_maintenance.csv', low_memory=False)

print(f"  Train: {train_df.shape}")
print(f"  Validate: {validate_df.shape}")
print(f"  Test: {test_df.shape}")

# ============================================================================
# 2. 定義特徵與目標
# ============================================================================
print("\n[2/6] 特徵選擇...")

# 預測目標：所有燃料的全速油耗 (統一為一個模型)
target_cols = ['ME_FULLSPEED_CONSUMP_HSHFO', 'ME_FULLSPEED_CONSUMP_VLSFO',
               'ME_FULLSPEED_CONSUMP_ULSFO', 'ME_FULLSPEED_CONSUMP_LSMGO',
               'ME_FULLSPEED_CONSUMP_BIO_HSFO']

# 燃料熱值 (MJ/kg) - 用來做跨燃料統一
fuel_heat_values = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
    'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
    'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}

# A 類特徵 (環境/航行 - 預測時可見)
a_features = [
    'AVG_SPEED', 'SPEED_THROUGH_WATER', 'ME_AVG_RPM', 'PROPELLER_SPEED',
    'FORE_DRAFT', 'AFTER_DRAFT', 'MID_DRAFT', 'DISPLACEMENT', 'CARGO_ON_BOARD',
    'WIND_SCALE', 'WIND_SPEED', 'WIND_DIRECTION', 'SEA_HEIGHT', 'SEA_DIRECTION',
    'SWELL_HEIGHT', 'SWELL_DIRECTION', 'SEA_WATER_TEMP', 'WATER_DEPTH',
    'TOTAL_DISTANCE', 'SEA_SPEED_DISTANCE', 'DIFF_STW_SOG_SLIP',
    'FULL_SPD_STW_SLIP', 'HOURS_FULL_SPEED', 'HOURS_TOTAL',
]

# 養護相關特徵 (時間距離 + 狀態)
maint_features = [
    'DAYS_SINCE_LAST_MAINT', 'DAYS_TO_NEXT_MAINT', 'LAST_MAINT_TYPE',
    'IS_MAINT_WINDOW', 'PROPELLER_STATE', 'HULL_STATE',
    'MAINT_TYPE_PP', 'MAINT_TYPE_UWI', 'MAINT_TYPE_UWI+PP',
    'MAINT_TYPE_UWC', 'MAINT_TYPE_UWC+PP', 'MAINT_TYPE_DD',
]

# 合併所有可用特徵
all_features = a_features + maint_features

# 過濾實際存在的特徵
available_features = [f for f in all_features if f in train_df.columns]
print(f"  可用特徵數: {len(available_features)}")

# ============================================================================
# 3. 準備訓練數據 (統一燃料當量)
# ============================================================================
print("\n[3/6] 準備訓練數據...")

# 方法：每行找到有效的燃料油耗值，換算為能量當量 (MJ/day)
# 這樣不同燃料的消耗可以用同一個模型預測

def prepare_target(df, target_cols, fuel_heat_values):
    """
    找到每行的有效油耗值，並記錄燃料類型
    返回: 有效行的索引、油耗值 (MT/day)、燃料類型、能量當量 (MJ/day)
    """
    rows = []
    for idx in df.index:
        for col in target_cols:
            val = df.loc[idx, col]
            try:
                numeric_val = float(val)
                if not np.isnan(numeric_val) and numeric_val > 0:
                    energy_equiv = numeric_val * fuel_heat_values[col] * 1000  # MJ/day
                    rows.append({
                        'orig_idx': idx,
                        'fuel_type': col,
                        'consumption_mt': numeric_val,
                        'energy_mj': energy_equiv,
                        'heat_value': fuel_heat_values[col],
                    })
                    break  # 每行只取一種燃料
            except (ValueError, TypeError):
                continue
    return pd.DataFrame(rows)

train_targets = prepare_target(train_df, target_cols, fuel_heat_values)
print(f"  有效訓練樣本: {len(train_targets)}")
print(f"  燃料分布:")
for ft in train_targets['fuel_type'].unique():
    count = (train_targets['fuel_type'] == ft).sum()
    print(f"    {ft}: {count}")

# 組合特徵矩陣
X_train = train_df.loc[train_targets['orig_idx'].values, available_features].copy()
y_train = train_targets['consumption_mt'].values  # 直接預測 MT/day

# 數值轉換 (處理可能的字串)
for col in available_features:
    X_train[col] = pd.to_numeric(X_train[col], errors='coerce')

# 加入燃料類型作為特徵 (因為不同燃料熱值不同，同樣能量消耗量不同)
fuel_type_map = {col: i for i, col in enumerate(target_cols)}
X_train['FUEL_TYPE_CODE'] = train_targets['fuel_type'].map(fuel_type_map).values
X_train['FUEL_HEAT_VALUE'] = train_targets['heat_value'].values

feature_cols_final = available_features + ['FUEL_TYPE_CODE', 'FUEL_HEAT_VALUE']
print(f"  最終特徵數: {len(feature_cols_final)}")

# ============================================================================
# 4. 訓練模型
# ============================================================================
print("\n[4/6] 訓練 XGBoost...")

# 過濾有效行 (排除 NaN target)
valid_mask = ~np.isnan(y_train)
X_train_clean = X_train[valid_mask].reset_index(drop=True)
y_train_clean = y_train[valid_mask]

print(f"  清洗後訓練樣本: {len(X_train_clean)}")

# Cross-validation
kf = KFold(n_splits=5, shuffle=True, random_state=42)
cv_scores = []

for fold, (train_idx, val_idx) in enumerate(kf.split(X_train_clean)):
    X_tr, X_va = X_train_clean.iloc[train_idx], X_train_clean.iloc[val_idx]
    y_tr, y_va = y_train_clean[train_idx], y_train_clean[val_idx]

    model = XGBRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)

    y_pred = model.predict(X_va)
    mae = mean_absolute_error(y_va, y_pred)
    rmse = np.sqrt(mean_squared_error(y_va, y_pred))
    r2 = r2_score(y_va, y_pred)
    cv_scores.append({'fold': fold+1, 'MAE': mae, 'RMSE': rmse, 'R2': r2})
    print(f"  Fold {fold+1}: MAE={mae:.3f}, RMSE={rmse:.3f}, R²={r2:.4f}")

cv_df = pd.DataFrame(cv_scores)
print(f"\n  CV 平均: MAE={cv_df['MAE'].mean():.3f}, RMSE={cv_df['RMSE'].mean():.3f}, R²={cv_df['R2'].mean():.4f}")

# 用全部訓練數據重新訓練
print("\n  用全部訓練數據重新訓練最終模型...")
final_model = XGBRegressor(
    n_estimators=500,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_alpha=0.1,
    reg_lambda=1.0,
    random_state=42,
    n_jobs=-1,
)
final_model.fit(X_train_clean, y_train_clean, verbose=False)

# ============================================================================
# 5. 驗證集表現
# ============================================================================
print("\n[5/6] 驗證集評估...")

validate_targets = prepare_target(validate_df, target_cols, fuel_heat_values)

if len(validate_targets) > 0:
    X_val = validate_df.loc[validate_targets['orig_idx'].values, available_features].copy()
    for col in available_features:
        X_val[col] = pd.to_numeric(X_val[col], errors='coerce')
    X_val['FUEL_TYPE_CODE'] = validate_targets['fuel_type'].map(fuel_type_map).values
    X_val['FUEL_HEAT_VALUE'] = validate_targets['heat_value'].values

    y_val = validate_targets['consumption_mt'].values
    valid_val_mask = ~np.isnan(y_val)

    if valid_val_mask.sum() > 0:
        X_val_clean = X_val[valid_val_mask]
        y_val_clean = y_val[valid_val_mask]

        y_val_pred = final_model.predict(X_val_clean)
        val_mae = mean_absolute_error(y_val_clean, y_val_pred)
        val_rmse = np.sqrt(mean_squared_error(y_val_clean, y_val_pred))
        val_r2 = r2_score(y_val_clean, y_val_pred)
        val_mape = np.mean(np.abs(y_val_clean - y_val_pred) / (y_val_clean + 1e-8)) * 100

        print(f"  驗證集樣本數: {len(y_val_clean)}")
        print(f"  MAE:  {val_mae:.3f} MT/day")
        print(f"  RMSE: {val_rmse:.3f} MT/day")
        print(f"  R²:   {val_r2:.4f}")
        print(f"  MAPE: {val_mape:.2f}%")
    else:
        print("  驗證集無有效目標值")
else:
    print("  驗證集無有效目標值 (可能被 HIDDEN)")

# ============================================================================
# 6. Feature Importance
# ============================================================================
print("\n[6/6] 特徵重要度 (Top 15)...")

importance = pd.Series(
    final_model.feature_importances_,
    index=feature_cols_final
).sort_values(ascending=False)

for i, (feat, imp) in enumerate(importance.head(15).items(), 1):
    bar = '█' * int(imp * 50)
    print(f"  {i:2d}. {feat:<30s} {imp:.4f} {bar}")

importance.to_csv('feature_importance.csv', header=['importance'])
print("\n  ✓ 完整特徵重要度已保存至 feature_importance.csv")

# ============================================================================
# 7. 預測 Test 集 (102 筆 PREDICT)
# ============================================================================
print("\n" + "="*80)
print("預測 102 筆 PREDICT")
print("="*80)

# 找出每個 PREDICT 對應的燃料類型
predictions = []
for idx in test_df.index:
    for col in target_cols:
        val = str(test_df.loc[idx, col])
        if val == 'PREDICT':
            ship_id = test_df.loc[idx, 'ship_id']
            day = test_df.loc[idx, 'NOON_UTC']

            # 準備特徵
            X_pred = test_df.loc[[idx], available_features].copy()
            for f in available_features:
                X_pred[f] = pd.to_numeric(X_pred[f], errors='coerce')
            X_pred['FUEL_TYPE_CODE'] = fuel_type_map[col]
            X_pred['FUEL_HEAT_VALUE'] = fuel_heat_values[col]

            predicted_value = final_model.predict(X_pred)[0]

            predictions.append({
                'ship_id': ship_id,
                'day': day,
                'fuel_type': col,
                'predicted_value': round(predicted_value, 2),
            })
            break  # 每行只有一個 PREDICT

print(f"\n  預測完成: {len(predictions)} 筆")

# 保存提交格式
submission = pd.DataFrame(predictions)
submission.to_csv('submission.csv', index=False)
print(f"  ✓ 已保存 submission.csv")

# 預測值統計
print(f"\n  預測值統計:")
print(f"    平均: {submission['predicted_value'].mean():.2f} MT/day")
print(f"    最小: {submission['predicted_value'].min():.2f} MT/day")
print(f"    最大: {submission['predicted_value'].max():.2f} MT/day")
print(f"    標準差: {submission['predicted_value'].std():.2f}")

# 按船舶統計
print(f"\n  按船舶:")
for ship in submission['ship_id'].unique():
    ship_data = submission[submission['ship_id'] == ship]
    print(f"    {ship}: {len(ship_data)} 筆, 平均 {ship_data['predicted_value'].mean():.2f} MT/day")

print("\n" + "="*80)
print("完成！")
print("="*80 + "\n")
