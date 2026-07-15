"""
XGBoost 訓練腳本
訓練 → 驗證 → 預測
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
import warnings
warnings.filterwarnings('ignore')

print("\n" + "="*80)
print("XGBoost 訓練管道")
print("="*80)

# ============================================================================
# 1. 加載數據
# ============================================================================
print("\n[1/5] 加載數據...")

train_df = pd.read_csv('data_train_with_maintenance.csv')
validate_df = pd.read_csv('data_validate_with_maintenance.csv')
submission_df = pd.read_csv('data_submission_with_maintenance.csv')

print(f"  Train:      {train_df.shape[0]:,} 行")
print(f"  Validate:   {validate_df.shape[0]:,} 行")
print(f"  Submission: {submission_df.shape[0]:,} 行")

# ============================================================================
# 2. 特徵準備
# ============================================================================
print("\n[2/5] 準備特徵...")

# 預測目標列
target_cols = ['ME_FULLSPEED_CONSUMP_HSHFO', 'ME_FULLSPEED_CONSUMP_VLSFO',
               'ME_FULLSPEED_CONSUMP_ULSFO', 'ME_FULLSPEED_CONSUMP_LSMGO']

# 排除的欄位
exclude_cols = ['ship_id', 'VOYAGE', 'NOON_UTC', 'De-identification Name',
                'LAST_MAINT_TYPE_NAME', 'hull_fouling_type', 'event_type', 'event_type_code',
                'cavitation_found', 'propeller_condition', 'hull_coating_condition'] + target_cols

# 特徵欄位
feature_cols = [col for col in train_df.columns if col not in exclude_cols]

print(f"  使用特徵數: {len(feature_cols)}")
print(f"  特徵範例: {feature_cols[:5]}")

# ============================================================================
# 3. 準備訓練數據
# ============================================================================
print("\n[3/5] 準備訓練數據...")

# Train 集
X_train = train_df[feature_cols].copy()
X_train = X_train.fillna(X_train.mean())

# 選擇有效的目標列（以 HSHFO 為主，其他補充）
y_train_values = []
for col in target_cols:
    valid = pd.to_numeric(train_df[col], errors='coerce')
    y_train_values.append(valid)

# 選擇最多非空值的列作為目標
y_train = None
for i, col in enumerate(target_cols):
    y_col = y_train_values[i]
    if y_col.notna().sum() > 100:
        y_train = y_col
        target_col = col
        break

if y_train is None:
    print("  ERROR: 無有效目標列")
    exit(1)

# 移除 NaN
valid_mask = y_train.notna()
X_train = X_train[valid_mask].reset_index(drop=True)
y_train = y_train[valid_mask].reset_index(drop=True)

print(f"  訓練樣本: {len(X_train)}")
print(f"  目標列: {target_col}")
print(f"  目標值範圍: {y_train.min():.2f} ~ {y_train.max():.2f}")

# Validate 集
X_validate = validate_df[feature_cols].copy()
X_validate = X_validate.fillna(X_train[feature_cols].mean())

y_validate_values = pd.to_numeric(validate_df[target_col], errors='coerce')
valid_mask_val = y_validate_values.notna()
X_validate = X_validate[valid_mask_val].reset_index(drop=True)
y_validate = y_validate_values[valid_mask_val].reset_index(drop=True)

print(f"  驗證樣本: {len(X_validate)}")

# ============================================================================
# 4. 訓練 XGBoost
# ============================================================================
print("\n[4/5] 訓練 XGBoost...")

model = GradientBoostingRegressor(
    max_depth=6,
    learning_rate=0.05,
    n_estimators=200,
    subsample=0.8,
    random_state=42,
    validation_fraction=0.2,
    n_iter_no_change=20
)

model.fit(X_train, y_train)

print(f"  訓練完成")

# ============================================================================
# 5. 驗證性能
# ============================================================================
print("\n[5/5] 驗證性能...")

y_pred_train = model.predict(X_train)
y_pred_validate = model.predict(X_validate)

mae_train = mean_absolute_error(y_train, y_pred_train)
rmse_train = np.sqrt(mean_squared_error(y_train, y_pred_train))
mae_val = mean_absolute_error(y_validate, y_pred_validate)
rmse_val = np.sqrt(mean_squared_error(y_validate, y_pred_validate))

print(f"\nTrain 集:")
print(f"  MAE:  {mae_train:.4f}")
print(f"  RMSE: {rmse_train:.4f}")

print(f"\nValidate 集:")
print(f"  MAE:  {mae_val:.4f}")
print(f"  RMSE: {rmse_val:.4f}")

# ============================================================================
# 6. 特徵重要性
# ============================================================================
print(f"\n特徵重要性 (Top 15):")
importance = pd.DataFrame({
    'feature': feature_cols,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

for i, (idx, row) in enumerate(importance.head(15).iterrows(), 1):
    print(f"  {i:2d}. {row['feature']:30s} {row['importance']:7.4f}")

# ============================================================================
# 7. 生成提交文件
# ============================================================================
print(f"\n生成提交文件...")

X_submit = submission_df[feature_cols].copy()
X_submit = X_submit.fillna(X_train[feature_cols].mean())

y_submit = model.predict(X_submit)

# 準備提交格式
submission_result = pd.DataFrame({
    'ship_id': submission_df['ship_id'],
    'day': submission_df['NOON_UTC'],
    'fuel_type': target_col,
    'predicted_value': y_submit
})

submission_result.to_csv('submission.csv', index=False)
print(f"  已保存 submission.csv ({len(submission_result)} 筆)")

print(f"\n提交預覽 (前 10 筆):")
print(submission_result.head(10).to_string())

print("\n" + "="*80)
print("完成！")
print("="*80 + "\n")
