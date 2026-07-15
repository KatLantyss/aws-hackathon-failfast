"""
特徵組合實驗 — 自動化比較不同特徵集對預測精度的影響
跑完會列出每組特徵的 Validate MAE / R²，找到最佳組合
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
print("特徵組合實驗 — 找最佳特徵集")
print("="*80)

# ============================================================================
# 加載數據
# ============================================================================
train_df = pd.read_csv('data_train_with_maintenance.csv', low_memory=False)
validate_df = pd.read_csv('data_validate_with_maintenance.csv', low_memory=False)

# 風力篩選
train_df['WIND_SCALE'] = pd.to_numeric(train_df['WIND_SCALE'], errors='coerce')
train_df = train_df[train_df['WIND_SCALE'] <= 4].reset_index(drop=True)
validate_df['WIND_SCALE'] = pd.to_numeric(validate_df['WIND_SCALE'], errors='coerce')
validate_df = validate_df[validate_df['WIND_SCALE'] <= 4].reset_index(drop=True)

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

train_targets = prepare_target(train_df)
val_targets = prepare_target(validate_df)

# ============================================================================
# 定義不同特徵組合
# ============================================================================

# 基本航行特徵 (距離/速度/時數 — 跟油耗最直接相關)
CORE = ['SEA_SPEED_DISTANCE', 'TOTAL_DISTANCE', 'ME_AVG_RPM', 'PROPELLER_SPEED',
        'HOURS_FULL_SPEED', 'HOURS_TOTAL']

# 船體狀態 (吃水/排水量/載貨)
HULL = ['FORE_DRAFT', 'AFTER_DRAFT', 'MID_DRAFT', 'DISPLACEMENT', 'CARGO_ON_BOARD']

# 速度相關
SPEED = ['AVG_SPEED', 'SPEED_THROUGH_WATER', 'DIFF_STW_SOG_SLIP', 'FULL_SPD_STW_SLIP']

# 天氣海況
WEATHER = ['WIND_SCALE', 'WIND_SPEED', 'WIND_DIRECTION', 'SEA_HEIGHT', 'SEA_DIRECTION',
           'SWELL_HEIGHT', 'SWELL_DIRECTION', 'SEA_WATER_TEMP', 'WATER_DEPTH']

# 養護特徵 (完整版)
MAINT_FULL = ['DAYS_SINCE_LAST_MAINT', 'LAST_MAINT_TYPE', 'IS_MAINT_WINDOW',
              'PROPELLER_STATE', 'MAINT_TYPE_PP', 'MAINT_TYPE_UWI', 'MAINT_TYPE_UWI+PP',
              'MAINT_TYPE_UWC', 'MAINT_TYPE_UWC+PP', 'MAINT_TYPE_DD']

# 養護特徵 (精簡版 — 只保留相關性高的)
MAINT_SLIM = ['DAYS_SINCE_LAST_MAINT', 'LAST_MAINT_TYPE']

# 額外衍生特徵 (之前的 feature_engineering.py 裡算的)
# 這裡直接在 runtime 計算
DERIVED = ['DRAFT_DIFF', 'LOAD_RATIO', 'CURRENT_EFFECT', 'FULL_SPEED_RATIO']

# 實驗組合
experiments = {
    'A: CORE only (6)':                         CORE,
    'B: CORE + HULL (11)':                      CORE + HULL,
    'C: CORE + HULL + SPEED (15)':              CORE + HULL + SPEED,
    'D: CORE + HULL + SPEED + WEATHER (24)':    CORE + HULL + SPEED + WEATHER,
    'E: D + MAINT_FULL (34)':                   CORE + HULL + SPEED + WEATHER + MAINT_FULL,
    'F: D + MAINT_SLIM (26)':                   CORE + HULL + SPEED + WEATHER + MAINT_SLIM,
    'G: D + MAINT_FULL + DERIVED (38)':         CORE + HULL + SPEED + WEATHER + MAINT_FULL + DERIVED,
    'H: CORE + MAINT_FULL (16)':                CORE + MAINT_FULL,
    'I: Top6 importance only':                  ['SEA_SPEED_DISTANCE', 'TOTAL_DISTANCE', 'ME_AVG_RPM',
                                                 'PROPELLER_SPEED', 'HOURS_FULL_SPEED', 'FUEL_HEAT_VALUE'],
}

# ============================================================================
# 計算衍生特徵
# ============================================================================
def add_derived(df):
    df = df.copy()
    for col in df.columns:
        if col not in ['ship_id', 'VOYAGE', 'NOON_UTC', 'hull_fouling_type', 'LAST_MAINT_TYPE_NAME']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    if 'FORE_DRAFT' in df.columns and 'AFTER_DRAFT' in df.columns:
        df['DRAFT_DIFF'] = abs(df['FORE_DRAFT'] - df['AFTER_DRAFT'])
    if 'CARGO_ON_BOARD' in df.columns and 'DISPLACEMENT' in df.columns:
        df['LOAD_RATIO'] = df['CARGO_ON_BOARD'] / (df['DISPLACEMENT'] + 1)
    if 'SPEED_THROUGH_WATER' in df.columns and 'AVG_SPEED' in df.columns:
        df['CURRENT_EFFECT'] = abs(df['SPEED_THROUGH_WATER'] - df['AVG_SPEED']) / (df['SPEED_THROUGH_WATER'] + 1)
    if 'HOURS_FULL_SPEED' in df.columns and 'HOURS_TOTAL' in df.columns:
        df['FULL_SPEED_RATIO'] = df['HOURS_FULL_SPEED'] / (df['HOURS_TOTAL'] + 1)
    return df

train_df = add_derived(train_df)
validate_df = add_derived(validate_df)

# ============================================================================
# 跑實驗
# ============================================================================
print(f"\n訓練樣本: {len(train_targets)}, 驗證樣本: {len(val_targets)}")
print()

results = []

for exp_name, feature_list in experiments.items():
    # 過濾實際存在的特徵
    available = [f for f in feature_list if f in train_df.columns]

    # 組裝 X_train
    X_train = train_df.loc[train_targets['orig_idx'].values, available].copy()
    y_train = train_targets['consumption_mt'].values
    for col in available:
        X_train[col] = pd.to_numeric(X_train[col], errors='coerce')
    X_train['FUEL_TYPE_CODE'] = train_targets['fuel_type'].map(fuel_type_map).values
    X_train['FUEL_HEAT_VALUE'] = train_targets['heat_value'].values

    # 組裝 X_val
    X_val = validate_df.loc[val_targets['orig_idx'].values, available].copy()
    y_val = val_targets['consumption_mt'].values
    for col in available:
        X_val[col] = pd.to_numeric(X_val[col], errors='coerce')
    X_val['FUEL_TYPE_CODE'] = val_targets['fuel_type'].map(fuel_type_map).values
    X_val['FUEL_HEAT_VALUE'] = val_targets['heat_value'].values

    # 過濾 NaN
    valid_train = ~np.isnan(y_train)
    valid_val = ~np.isnan(y_val)
    X_train_c = X_train[valid_train].reset_index(drop=True)
    y_train_c = y_train[valid_train]
    X_val_c = X_val[valid_val]
    y_val_c = y_val[valid_val]

    # 訓練
    model = XGBRegressor(
        n_estimators=800, max_depth=7, learning_rate=0.03,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.5, reg_lambda=2.0, min_child_weight=5, gamma=0.1,
        random_state=42, n_jobs=-1,
    )
    model.fit(X_train_c, y_train_c, verbose=False)

    # 驗證
    y_pred = model.predict(X_val_c)
    mae = mean_absolute_error(y_val_c, y_pred)
    rmse = np.sqrt(mean_squared_error(y_val_c, y_pred))
    r2 = r2_score(y_val_c, y_pred)

    # MAPE (>10 MT/day)
    high = y_val_c > 10
    mape = np.mean(np.abs(y_val_c[high] - y_pred[high]) / y_val_c[high]) * 100 if high.sum() > 0 else 0

    # 準確率 (誤差 ≤ 10 MT/day)
    within_10 = (np.abs(y_val_c - y_pred) <= 10).sum() / len(y_val_c) * 100

    results.append({
        'Experiment': exp_name,
        'Features': len(available) + 2,  # +2 for FUEL_TYPE_CODE, FUEL_HEAT_VALUE
        'MAE': mae,
        'RMSE': rmse,
        'R2': r2,
        'MAPE%': mape,
        'Within10MT%': within_10,
    })

    print(f"  {exp_name}")
    print(f"    特徵數={len(available)+2}, MAE={mae:.3f}, R²={r2:.4f}, MAPE={mape:.1f}%, ≤10MT={within_10:.1f}%")
    print()

# ============================================================================
# 結果排名
# ============================================================================
print("\n" + "="*80)
print("實驗結果排名 (按 Val MAE 排序)")
print("="*80)

results_df = pd.DataFrame(results).sort_values('MAE')
print()
print(f"{'排名':<4} {'實驗':<40} {'特徵':<5} {'MAE':<8} {'R²':<8} {'MAPE%':<7} {'≤10MT%':<7}")
print("-" * 80)
for i, row in enumerate(results_df.itertuples(), 1):
    star = ' ⭐' if i == 1 else ''
    print(f"{i:<4} {row.Experiment:<40} {row.Features:<5} {row.MAE:<8.3f} {row.R2:<8.4f} {row._6:<7.1f} {row._7:<7.1f}{star}")

results_df.to_csv('experiment_results.csv', index=False)
print(f"\n✓ 結果已保存至 experiment_results.csv")

# ============================================================================
# 最佳組合 vs 最差組合差異
# ============================================================================
best = results_df.iloc[0]
worst = results_df.iloc[-1]
print(f"\n最佳: {best['Experiment']} (MAE={best['MAE']:.3f}, R²={best['R2']:.4f})")
print(f"最差: {worst['Experiment']} (MAE={worst['MAE']:.3f}, R²={worst['R2']:.4f})")
print(f"改善幅度: MAE 降低 {worst['MAE'] - best['MAE']:.3f} MT/day")

print("\n" + "="*80 + "\n")
