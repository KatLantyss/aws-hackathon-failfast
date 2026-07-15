"""
船舶推進效能預測 - 特徵工程工作流
流程：資料探索 → 分割 train/validate/test → 指標代表性檢驗 → 衍生指標計算
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
import warnings
warnings.filterwarnings('ignore')

# 設置中文字體
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ============================================================================
# 1. 資料加載與探索
# ============================================================================

def load_and_explore_data():
    """加載並探索原始數據"""
    print("="*80)
    print("第1步：加載和探索數據")
    print("="*80)

    df = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv')
    print(f"\n✓ 加載完成: {df.shape[0]} 行, {df.shape[1]} 列")

    # 基本統計
    print(f"\n船舶類型:")
    print(f"  訓練船 (S1-S12): {df[df['De-identification Name'].str.match(r'S[1-9]|S1[0-2]')].shape[0]} 行")
    print(f"  預測船 (S21-S23): {df[df['De-identification Name'].str.match(r'S2[1-3]')].shape[0]} 行")

    print(f"\n缺失值統計 (前20列):")
    missing = df.isnull().sum()
    for col in missing.head(20).index:
        pct = 100 * missing[col] / len(df)
        if missing[col] > 0:
            print(f"  {col}: {missing[col]} ({pct:.1f}%)")

    return df


# ============================================================================
# 2. 資料分割
# ============================================================================

def split_train_validate_test(df):
    """
    基於船舶類型和時間分割資料
    - Train: S1-S12 (訓練船全部數據)
    - Validate: S21-S23 養護前數據 (用於驗證模型)
    - Test: S21-S23 養護後需預測的數據
    """
    print("\n" + "="*80)
    print("第2步：資料分割")
    print("="*80)

    # 分離訓練船和預測船
    train_df = df[df['De-identification Name'].str.match(r'S[1-9]|S1[0-2]')].copy()
    predict_df = df[df['De-identification Name'].str.match(r'S2[1-3]')].copy()

    print(f"\nTrain (S1-S12): {train_df.shape[0]} 行")
    print(f"Predict (S21-S23): {predict_df.shape[0]} 行")

    # 在預測船中分離有預測標記的行 (需預測的數據)
    # 這裡假設 'PREDICT' 標記在某個燃料消耗欄位中出現
    predict_cols = ['ME_FULLSPEED_CONSUMP_HSHFO', 'ME_FULLSPEED_CONSUMP_VLSFO',
                    'ME_FULLSPEED_CONSUMP_ULSFO', 'ME_FULLSPEED_CONSUMP_LSMGO']

    test_mask = predict_df[predict_cols].astype(str).eq('PREDICT').any(axis=1)
    test_df = predict_df[test_mask].copy()
    validate_df = predict_df[~test_mask].copy()

    print(f"Validate (預測船養護前): {validate_df.shape[0]} 行")
    print(f"Test (預測船需預測): {test_df.shape[0]} 行")

    return train_df, validate_df, test_df


# ============================================================================
# 3. 指標代表性檢驗
# ============================================================================

def analyze_feature_representativeness(train_df):
    """
    檢驗每個數值指標的代表性：
    - 缺失率
    - 數據方差 (變異程度)
    - 與預測目標的相關性
    """
    print("\n" + "="*80)
    print("第3步：指標代表性檢驗")
    print("="*80)

    # 選擇數值欄位 (排除ID和字符串欄位)
    numeric_cols = train_df.select_dtypes(include=[np.number]).columns.tolist()
    numeric_cols = [col for col in numeric_cols if col not in ['VOYAGE', 'NOON_UTC']]

    # 預測目標 (優先級：HSHFO > VLSFO > ULSFO > LSMGO)
    target_candidates = ['ME_FULLSPEED_CONSUMP_HSHFO', 'ME_FULLSPEED_CONSUMP_VLSFO',
                        'ME_FULLSPEED_CONSUMP_ULSFO', 'ME_FULLSPEED_CONSUMP_LSMGO']

    # 找到有效的目標列
    target_col = None
    for col in target_candidates:
        if col in train_df.columns:
            valid_target = train_df[col].notna() & (train_df[col] != 'HIDDEN')
            if valid_target.sum() > 100:  # 至少100個有效值
                target_col = col
                print(f"\n使用預測目標: {target_col} ({valid_target.sum()} 個有效值)")
                break

    if target_col is None:
        print("警告：找不到有效的預測目標，將跳過相關性分析")
        target_series = None
    else:
        try:
            target_series = pd.to_numeric(train_df[target_col], errors='coerce')
        except:
            target_series = None

    # 計算特徵統計
    feature_stats = []
    for col in numeric_cols:
        try:
            series = pd.to_numeric(train_df[col], errors='coerce')

            stats = {
                'Feature': col,
                'Missing_Rate': 100 * series.isna().sum() / len(series),
                'Std_Dev': series.std(),
                'CV': series.std() / series.mean() if series.mean() != 0 else np.nan,  # 變異係數
                'Valid_Count': series.notna().sum()
            }

            # 與目標的相關性
            if target_series is not None:
                try:
                    corr = series.corr(target_series)
                    stats['Correlation_with_Target'] = corr if not np.isnan(corr) else 0
                except:
                    stats['Correlation_with_Target'] = 0

            feature_stats.append(stats)
        except:
            pass

    feature_df = pd.DataFrame(feature_stats)

    # 排序並展示
    feature_df = feature_df.sort_values('Valid_Count', ascending=False)

    print("\n代表性指標統計 (按有效值數量排序):")
    print(feature_df.to_string(index=False, max_colwidth=30))

    # 儲存到 CSV
    feature_df.to_csv('feature_representativeness.csv', index=False)
    print("\n✓ 詳細統計已保存至 feature_representativeness.csv")

    return feature_df, numeric_cols


# ============================================================================
# 4. 衍生指標計算
# ============================================================================

def compute_derived_features(df):
    """
    計算具有物理意義的衍生指標
    基於海事工程原理
    """
    print("\n" + "="*80)
    print("第4步：計算衍生指標")
    print("="*80)

    df_derived = df.copy()

    # 將可能是字符串的數值列轉換為數值
    numeric_cols = df_derived.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        df_derived[col] = pd.to_numeric(df_derived[col], errors='coerce')

    derived_features = []

    # 1. 吃水平均值 (關係到排水量和船體阻力)
    if all(col in df_derived.columns for col in ['FORE_DRAFT', 'AFTER_DRAFT']):
        df_derived['AVG_DRAFT'] = (df_derived['FORE_DRAFT'] + df_derived['AFTER_DRAFT']) / 2
        derived_features.append('AVG_DRAFT')
        print("✓ AVG_DRAFT: 平均吃水")

    # 2. 吃水差異 (船的水平衡狀態)
    if all(col in df_derived.columns for col in ['FORE_DRAFT', 'AFTER_DRAFT']):
        df_derived['DRAFT_DIFF'] = abs(df_derived['FORE_DRAFT'] - df_derived['AFTER_DRAFT'])
        derived_features.append('DRAFT_DIFF')
        print("✓ DRAFT_DIFF: 首尾吃水差")

    # 3. 風浪海況綜合指標
    if all(col in df_derived.columns for col in ['WIND_SPEED', 'SEA_HEIGHT']):
        df_derived['SEA_STATE'] = df_derived['WIND_SPEED'] * 0.5 + df_derived['SEA_HEIGHT'] * 0.5
        derived_features.append('SEA_STATE')
        print("✓ SEA_STATE: 海況綜合指標")

    # 4. 主機性能效率 (比油耗)
    if 'SFOC' in df_derived.columns:
        df_derived['ENGINE_EFFICIENCY'] = 1 / (df_derived['SFOC'] + 1)  # 避免除以0
        derived_features.append('ENGINE_EFFICIENCY')
        print("✓ ENGINE_EFFICIENCY: 主機效率")

    # 5. 螺旋槳滑差 (推進效率)
    if 'ME_SLIP' in df_derived.columns:
        df_derived['PROPELLER_EFFICIENCY'] = 1 - (df_derived['ME_SLIP'] / 100)
        derived_features.append('PROPELLER_EFFICIENCY')
        print("✓ PROPELLER_EFFICIENCY: 螺旋槳效率")

    # 6. 推力係數與轉速比
    if all(col in df_derived.columns for col in ['THRUST_QUOTIENT', 'PROPELLER_SPEED']):
        df_derived['THRUST_RPM_RATIO'] = df_derived['THRUST_QUOTIENT'] * (df_derived['PROPELLER_SPEED'] / 100)
        derived_features.append('THRUST_RPM_RATIO')
        print("✓ THRUST_RPM_RATIO: 推力轉速比")

    # 7. 載重率 (排水量與載貨的比例)
    if all(col in df_derived.columns for col in ['CARGO_ON_BOARD', 'DISPLACEMENT']):
        df_derived['LOAD_RATIO'] = df_derived['CARGO_ON_BOARD'] / (df_derived['DISPLACEMENT'] + 1)
        derived_features.append('LOAD_RATIO')
        print("✓ LOAD_RATIO: 載重率")

    # 8. 主機負荷強度
    if 'LOAD_PCT' in df_derived.columns:
        df_derived['LOAD_PCT_SQUARED'] = (df_derived['LOAD_PCT'] / 100) ** 2
        derived_features.append('LOAD_PCT_SQUARED')
        print("✓ LOAD_PCT_SQUARED: 主機負荷平方")

    # 9. 對水對地速度差異比例 (洋流強度代理)
    if all(col in df_derived.columns for col in ['SPEED_THROUGH_WATER', 'AVG_SPEED']):
        df_derived['CURRENT_EFFECT'] = abs(df_derived['SPEED_THROUGH_WATER'] - df_derived['AVG_SPEED']) / (df_derived['SPEED_THROUGH_WATER'] + 1)
        derived_features.append('CURRENT_EFFECT')
        print("✓ CURRENT_EFFECT: 洋流效應指數")

    # 10. 全速時段所佔比例
    if all(col in df_derived.columns for col in ['HOURS_FULL_SPEED', 'HOURS_TOTAL']):
        df_derived['FULL_SPEED_RATIO'] = df_derived['HOURS_FULL_SPEED'] / (df_derived['HOURS_TOTAL'] + 1)
        derived_features.append('FULL_SPEED_RATIO')
        print("✓ FULL_SPEED_RATIO: 全速時段比例")

    print(f"\n計算完成: {len(derived_features)} 個衍生指標")

    return df_derived, derived_features


# ============================================================================
# 5. 主函式
# ============================================================================

def main():
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*20 + "船舶推進效能預測 - 特徵工程工作流" + " "*24 + "║")
    print("╚" + "="*78 + "╝")

    # Step 1: 加載資料
    df = load_and_explore_data()

    # Step 2: 分割資料
    train_df, validate_df, test_df = split_train_validate_test(df)

    # Step 3: 檢驗指標代表性
    feature_df, numeric_cols = analyze_feature_representativeness(train_df)

    # Step 4: 計算衍生指標
    train_df_derived, derived_features = compute_derived_features(train_df)
    validate_df_derived, _ = compute_derived_features(validate_df)
    test_df_derived, _ = compute_derived_features(test_df)

    # 匯總結果
    print("\n" + "="*80)
    print("總結")
    print("="*80)
    print(f"\n訓練集特徵數: {train_df_derived.shape[1]} 列")
    print(f"  - 原始指標: ~{len(numeric_cols)}")
    print(f"  - 衍生指標: {len(derived_features)}")
    print(f"\n數據集分割:")
    print(f"  - Train: {train_df_derived.shape[0]} 行")
    print(f"  - Validate: {validate_df_derived.shape[0]} 行")
    print(f"  - Test: {test_df_derived.shape[0]} 行")

    # 保存分割後的數據
    train_df_derived.to_csv('data_train.csv', index=False)
    validate_df_derived.to_csv('data_validate.csv', index=False)
    test_df_derived.to_csv('data_test.csv', index=False)
    print("\n✓ 分割後的數據已保存")

    print("\n" + "="*80)
    print("下一步：")
    print("  1. 檢查 feature_representativeness.csv 中哪些指標相關性最高")
    print("  2. 基於相關性和缺失率選擇關鍵指標")
    print("  3. 訓練預測模型 (Random Forest / XGBoost / Neural Network)")
    print("  4. 驗證在 Validate 集上的性能")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
