"""
改進版特徵工程：補充時間距離特徵 + 特徵篩選準備
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

print("\n" + "="*80)
print("改進版特徵工程 v2：完整時間特徵 + 特徵篩選")
print("="*80)

# 加載之前的分割數據
train_df = pd.read_csv('data_train_with_maintenance.csv')
validate_df = pd.read_csv('data_validate_with_maintenance.csv')
submission_df = pd.read_csv('data_test_with_maintenance.csv')  # 改為 test

print(f"\n加載: Train {train_df.shape[0]} + Validate {validate_df.shape[0]} + Submit {submission_df.shape[0]}")

# ============================================================================
# 補充完整時間距離特徵
# ============================================================================
def add_time_distance_features(df):
    """添加完整的時間距離特徵"""
    df = df.copy()

    # 確保 DAYS_SINCE_LAST_MAINT 存在（應該已有）
    if 'DAYS_SINCE_LAST_MAINT' not in df.columns:
        df['DAYS_SINCE_LAST_MAINT'] = 0

    # 新增：DAYS_UNTIL_NEXT_MAINT（漏掉的特徵）
    if 'DAYS_TO_NEXT_MAINT' in df.columns:
        df['DAYS_UNTIL_NEXT_MAINT'] = df['DAYS_TO_NEXT_MAINT']
    else:
        df['DAYS_UNTIL_NEXT_MAINT'] = 0

    # 改進：養護窗口定義（更精確）
    # 養護前 3 天 ~ 養護後 7 天
    df['IS_MAINT_PRE_WINDOW'] = (
        (df['DAYS_SINCE_LAST_MAINT'] < 3) & (df['DAYS_SINCE_LAST_MAINT'] >= 0)
    ).astype(int)

    df['IS_MAINT_POST_WINDOW'] = (
        (df['DAYS_SINCE_LAST_MAINT'] <= 7) & (df['DAYS_SINCE_LAST_MAINT'] >= 0)
    ).astype(int)

    # 新增：距養護的距離（無量綱化）
    df['MAINT_DISTANCE_RATIO'] = (
        df['DAYS_SINCE_LAST_MAINT'] / (df['DAYS_SINCE_LAST_MAINT'] + df['DAYS_UNTIL_NEXT_MAINT'] + 1)
    )

    # 新增：養護密度（該時間段附近的養護次數）
    # 這個需要在分組時計算，先做簡化版
    df['MAINT_FREQUENCY'] = df['LAST_MAINT_TYPE'].notna().astype(int)

    return df

print("\n補充時間特徵:")
print("  [OK] DAYS_UNTIL_NEXT_MAINT (距下次養護天數)")
print("  [OK] IS_MAINT_PRE_WINDOW (養護前 0-3 天)")
print("  [OK] IS_MAINT_POST_WINDOW (養護後 0-7 天)")
print("  [OK] MAINT_DISTANCE_RATIO (養護循環內相對位置)")
print("  [OK] MAINT_FREQUENCY (該期間是否有養護)")

train_df = add_time_distance_features(train_df)
validate_df = add_time_distance_features(validate_df)
submission_df = add_time_distance_features(submission_df)

# ============================================================================
# 特徵重要性預測（基於相關性）
# ============================================================================
print("\n" + "="*80)
print("特徵重要性評估（基於訓練集）")
print("="*80)

# 目標列
target_col = 'ME_FULLSPEED_CONSUMP_HSHFO'
y = pd.to_numeric(train_df[target_col], errors='coerce')
y_valid = y.notna()

# 計算每個特徵與目標的相關性
exclude_cols = ['ship_id', 'VOYAGE', 'NOON_UTC', 'De-identification Name',
                'LAST_MAINT_TYPE_NAME', 'hull_fouling_type', 'event_type',
                'event_type_code', 'cavitation_found', 'propeller_condition',
                'hull_coating_condition',
                'ME_FULLSPEED_CONSUMP_HSHFO', 'ME_FULLSPEED_CONSUMP_VLSFO',
                'ME_FULLSPEED_CONSUMP_ULSFO', 'ME_FULLSPEED_CONSUMP_LSMGO']

feature_cols = [col for col in train_df.columns if col not in exclude_cols]

correlations = {}
for col in feature_cols:
    try:
        x = pd.to_numeric(train_df[col], errors='coerce')
        # 只計算有效的行
        valid_mask = x.notna() & y_valid
        if valid_mask.sum() > 10:
            corr = x[valid_mask].corr(y[valid_mask])
            correlations[col] = abs(corr) if not np.isnan(corr) else 0
        else:
            correlations[col] = 0
    except:
        correlations[col] = 0

# 排序
corr_df = pd.DataFrame(list(correlations.items()), columns=['feature', 'correlation']).sort_values('correlation', ascending=False)

print(f"\n前 25 個最相關特徵:\n")
for i, (_, row) in enumerate(corr_df.head(25).iterrows(), 1):
    print(f"{i:2d}. {row['feature']:35s} {row['correlation']:7.4f}")

print(f"\n後 10 個低相關特徵 (可考慮移除):\n")
for i, (_, row) in enumerate(corr_df.tail(10).iterrows(), 1):
    print(f"    {row['feature']:35s} {row['correlation']:7.4f}")

# ============================================================================
# 特徵分組
# ============================================================================
print("\n" + "="*80)
print("特徵分組")
print("="*80)

# 時間特徵
time_features = ['DAYS_SINCE_LAST_MAINT', 'DAYS_UNTIL_NEXT_MAINT',
                 'IS_MAINT_PRE_WINDOW', 'IS_MAINT_POST_WINDOW', 'MAINT_DISTANCE_RATIO']

# 養護類型特徵
maint_type_features = [col for col in feature_cols if col.startswith('MAINT_TYPE_')]

# 污損狀態特徵
pollution_features = ['PROPELLER_STATE', 'hull_coating_condition_code', 'propeller_condition_code', 'cavitation_code']

# 環境特徵
env_features = [col for col in feature_cols if any(keyword in col for keyword in
                ['WIND', 'SEA', 'WATER', 'SWELL', 'DRAFT', 'TEMP', 'DEPTH'])]

# 運營特徵
ops_features = [col for col in feature_cols if any(keyword in col for keyword in
                ['SPEED', 'RPM', 'DISTANCE', 'HOURS', 'CARGO', 'DISPLACEMENT'])]

print(f"\n時間特徵 ({len(time_features)}): {time_features}")
print(f"\n養護類型 ({len(maint_type_features)}): {maint_type_features}")
print(f"\n污損狀態 ({len(pollution_features)}): {pollution_features}")
print(f"\n環境特徵 ({len(env_features)}): {env_features[:5]}... 等")
print(f"\n運營特徵 ({len(ops_features)}): {ops_features[:5]}... 等")

# ============================================================================
# 篩選策略
# ============================================================================
print("\n" + "="*80)
print("特徵篩選建議")
print("="*80)

print("\n推薦篩選策略 (分階段):")
print("\n第 1 階段：保留所有特徵")
print("  → 建立基準")
print("\n第 2 階段：移除低相關特徵 (correlation < 0.05)")
low_corr = corr_df[corr_df['correlation'] < 0.05]['feature'].tolist()[:5]
print(f"  → 可移除: {', '.join(low_corr)}")
print("\n第 3 階段：保留核心特徵 (correlation > 0.15)")
print("  → 保留: 時間 + 環境 + 運營特徵")
print("\n第 4 階段：特徵工程")
print("  → 增加: DAYS_SINCE × WIND_SPEED 等交互項")

# ============================================================================
# 保存改進版數據
# ============================================================================
train_df.to_csv('data_train_v2.csv', index=False)
validate_df.to_csv('data_validate_v2.csv', index=False)
submission_df.to_csv('data_submission_v2.csv', index=False)  # submission

print("\n" + "="*80)
print("[OK] 已保存改進版數據 (v2):")
print(f"  - data_train_v2.csv ({train_df.shape[1]} 列)")
print(f"  - data_validate_v2.csv ({validate_df.shape[1]} 列)")
print(f"  - data_submission_v2.csv ({submission_df.shape[1]} 列)")
print("="*80 + "\n")

# 保存特徵相關性供後續使用
corr_df.to_csv('feature_correlations.csv', index=False)
print("[OK] 特徵相關性已保存：feature_correlations.csv")
