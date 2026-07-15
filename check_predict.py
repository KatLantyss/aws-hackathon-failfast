import pandas as pd
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)

# 看預測船
predict_ships = ['S21', 'S22', 'S23']
predict_vt = vt[vt['De-identification Name'].isin(predict_ships)].copy()

predict_cols = ['ME_FULLSPEED_CONSUMP_HSHFO', 'ME_FULLSPEED_CONSUMP_VLSFO',
                'ME_FULLSPEED_CONSUMP_ULSFO', 'ME_FULLSPEED_CONSUMP_LSMGO']
h_cols = ['HORSE_POWER', 'LOAD_PCT', 'SFOC', 'ME_SLIP', 'THRUST', 'THRUST_QUOTIENT']

print("="*80)
print("PREDICT 和 HIDDEN 在原始檔案中的呈現")
print("="*80)

# 找一行有 PREDICT 的
for idx, row in predict_vt.iterrows():
    has_predict = False
    for col in predict_cols:
        if str(row[col]) == 'PREDICT':
            has_predict = True
            break
    if has_predict:
        print("\n[範例] 有 PREDICT 標記的行:\n")
        print(f"ship_id: {row['De-identification Name']}")
        print(f"NOON_UTC: {row['NOON_UTC']}")

        print("\n燃料消耗欄位 (T 類):")
        for col in predict_cols:
            val = row[col]
            print(f"  {col}: {val}")

        print("\n主機性能欄位 (H 類，在預測期被隱藏):")
        for col in h_cols:
            val = row[col]
            print(f"  {col}: {val}")

        break

print("\n" + "="*80)
print("MASK 的三種呈現方式")
print("="*80)

print("""
1. "PREDICT" (需要預測)
   ├─ 在 CSV 檔案中直接顯示: \"PREDICT\"
   ├─ 無法作為訓練標籤（不是數值）
   ├─ 表示該位置的油耗值被遮蔽
   └─ 這 102 個就是我們要預測的目標

2. "HIDDEN" (存在但不提供)
   ├─ 在 CSV 檔案中直接顯示: \"HIDDEN\"
   ├─ 表示資料存在但被遮蔽
   ├─ 只出現在預測船的某些期間
   └─ 無法用作模型特徵（因為值不知道）

3. 空值 (原始即為缺失)
   ├─ 在 CSV 檔案中顯示為空白
   ├─ 表示該位置原本就沒資料
   └─ 用 NaN 或空字符串表示
""")

print("\n" + "="*80)
print("對我們的影響")
print("="*80)

print("""
訓練集 (S1-S12):
  ✓ 所有欄位都有實際數值或空值
  ✓ 可以直接用於訓練

驗證集 (S21-S23 非 PREDICT 部分):
  ✗ H 類欄位顯示 "HIDDEN"
  → 無法用這些特徵
  ✓ 但可以用 A 類特徵驗證

測試集 (S21-S23 PREDICT 部分):
  ✗ 油耗欄位顯示 "PREDICT"
  → 無法用作標籤
  ✓ 但可以用 A 類特徵做預測

解決方案:
  1. 訓練時只用 A 類 + 衍生 + 維護特徵
  2. 在驗證集上測試 (忽略 HIDDEN 的 H 類特徵)
  3. 對 Test 集的 PREDICT 行做預測
""")

# 統計各類型
print("\n" + "="*80)
print("統計")
print("="*80)

# 訓練船有實際值
train_ships = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12']
train_vt = vt[vt['De-identification Name'].isin(train_ships)]

# 檢查 SFOC 值
sfoc_values = pd.to_numeric(train_vt['SFOC'], errors='coerce')
print(f"\n訓練集 SFOC:")
print(f"  有實際值: {sfoc_values.notna().sum()}")
print(f"  平均值: {sfoc_values.mean():.1f} g/kWh")

sfoc_hshfo = pd.to_numeric(train_vt['ME_FULLSPEED_CONSUMP_HSHFO'], errors='coerce')
print(f"\n訓練集 ME_FULLSPEED_CONSUMP_HSHFO:")
print(f"  有實際值: {sfoc_hshfo.notna().sum()}")
print(f"  平均值: {sfoc_hshfo.mean():.2f} MT/day")
print(f"  範圍: {sfoc_hshfo.min():.2f} ~ {sfoc_hshfo.max():.2f}")
