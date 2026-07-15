# 下一步：模型訓練與預測

已完成：
✓ 特徵工程：vt_fd + maintenance 融合
✓ 時序特徵生成：DAYS_SINCE_LAST_MAINT, 養護類型編碼等
✓ 數據分割：Train (16,944) / Validate (4,236) / Submission (102)

## 需要的操作

### 1. 環境準備
```bash
pip install pandas numpy scikit-learn xgboost lightgbm
```

### 2. 訓練模型（在本機 Jupyter 或 Python 中）

```python
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

# 加載數據
train_df = pd.read_csv('data_train_with_maintenance.csv')
validate_df = pd.read_csv('data_validate_with_maintenance.csv')
submission_df = pd.read_csv('data_submission_with_maintenance.csv')

# 特徵列（排除 ID 和目標列）
exclude_cols = ['ship_id', 'VOYAGE', 'NOON_UTC', 'De-identification Name',
                'LAST_MAINT_TYPE_NAME', 'hull_fouling_type', 'event_type', 
                'event_type_code', 'cavitation_found', 'propeller_condition', 
                'hull_coating_condition', 'ME_FULLSPEED_CONSUMP_HSHFO', 
                'ME_FULLSPEED_CONSUMP_VLSFO', 'ME_FULLSPEED_CONSUMP_ULSFO', 
                'ME_FULLSPEED_CONSUMP_LSMGO']

feature_cols = [col for col in train_df.columns if col not in exclude_cols]

# 準備數據
X_train = train_df[feature_cols].fillna(train_df[feature_cols].mean())
y_train = pd.to_numeric(train_df['ME_FULLSPEED_CONSUMP_HSHFO'], errors='coerce')
valid_mask = y_train.notna()
X_train = X_train[valid_mask]
y_train = y_train[valid_mask]

X_validate = validate_df[feature_cols].fillna(X_train.mean())
y_validate = pd.to_numeric(validate_df['ME_FULLSPEED_CONSUMP_HSHFO'], errors='coerce')
valid_mask_val = y_validate.notna()
X_validate = X_validate[valid_mask_val]
y_validate = y_validate[valid_mask_val]

# 訓練模型
model = GradientBoostingRegressor(
    max_depth=6,
    learning_rate=0.05,
    n_estimators=200,
    subsample=0.8,
    random_state=42
)
model.fit(X_train, y_train)

# 驗證
y_pred = model.predict(X_validate)
mae = mean_absolute_error(y_validate, y_pred)
rmse = np.sqrt(mean_squared_error(y_validate, y_pred))
print(f"Validate MAE: {mae:.4f}, RMSE: {rmse:.4f}")

# 預測提交集
X_submit = submission_df[feature_cols].fillna(X_train.mean())
y_submit = model.predict(X_submit)

# 生成提交文件
submission = pd.DataFrame({
    'ship_id': submission_df['ship_id'],
    'day': submission_df['NOON_UTC'],
    'fuel_type': 'ME_FULLSPEED_CONSUMP_HSHFO',
    'predicted_value': y_submit
})

submission.to_csv('submission.csv', index=False)
print(f"提交文件已生成：submission.csv ({len(submission)} 筆)")
```

### 3. 提交格式

```csv
ship_id,day,fuel_type,predicted_value
S21,1383,ME_FULLSPEED_CONSUMP_HSHFO,33.45
S21,1390,ME_FULLSPEED_CONSUMP_HSHFO,32.87
...
```

**共 102 筆**

## 特徵說明

### 原始特徵 (A 類 - 環境/航行)
- AVG_SPEED, SPEED_THROUGH_WATER, ME_AVG_RPM, PROPELLER_SPEED
- FORE_DRAFT, AFTER_DRAFT, MID_DRAFT, DISPLACEMENT
- CARGO_ON_BOARD, WIND_SCALE, WIND_SPEED, SEA_HEIGHT, SEA_WATER_TEMP 等

### 衍生指標
- AVG_DRAFT, DRAFT_DIFF, SEA_STATE 等

### 養護時序特徵
- DAYS_SINCE_LAST_MAINT: 距上次養護的天數（污損累積度代理）
- IS_MAINT_WINDOW: 是否在養護前後窗口內
- MAINT_TYPE_*: 養護類型 One-Hot 編碼 (PP, UWC, DD 等)
- PROPELLER_STATE: 螺旋槳狀態 (Good=3, Fair=2, Poor=1)

## 可能的改進

1. **LightGBM** - 替代 GradientBoosting，可能性能更好
2. **Ensemble** - 結合多個模型 (Boosting + NN + Linear)
3. **特徵調優** - 移除低相關特徵，計算更多交互項
4. **超參數調優** - 用 Optuna 或 GridSearch
5. **處理異常值** - 預測值 < 0 的異常值處理

## 當前數據統計

- **訓練集目標值 (ME_FULLSPEED_CONSUMP_HSHFO)**
  - 平均值: 33.39 MT/day
  - 範圍: -27.81 ~ 162.90 (有異常值，需要清理)
  
- **特徵數: 52**
  - 環境/航行: 25
  - 衍生指標: 10
  - 養護時序: 17

---

下一步請在本地環境運行上述 Python 代碼，生成 submission.csv 進行提交！
