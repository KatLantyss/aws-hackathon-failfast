import pandas as pd
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)

predict_ships = ['S21', 'S22', 'S23']
predict_vt = vt[vt['De-identification Name'].isin(predict_ships)].copy()

print("="*80)
print("PREDICT vs HIDDEN - 完全澄清")
print("="*80)

print("\n[要預測的] PREDICT - 油耗欄位被遮蔽")
print("-"*80)

predict_cols = ['ME_FULLSPEED_CONSUMP_HSHFO', 'ME_FULLSPEED_CONSUMP_VLSFO',
                'ME_FULLSPEED_CONSUMP_ULSFO', 'ME_FULLSPEED_CONSUMP_LSMGO']

for col in predict_cols:
    predict_count = (predict_vt[col].astype(str) == 'PREDICT').sum()
    print(f"\n{col}:")
    print(f"  PREDICT 筆數: {predict_count}")
    if predict_count > 0:
        sample_rows = predict_vt[predict_vt[col].astype(str) == 'PREDICT'].head(3)
        for idx, row in sample_rows.iterrows():
            print(f"    例: {row['De-identification Name']} Day {row['NOON_UTC']} -> PREDICT")

print("\n\n[無法用的] HIDDEN - 主機性能欄位被遮蔽")
print("-"*80)

h_cols = ['HORSE_POWER', 'LOAD_PCT', 'SFOC', 'ME_SLIP', 'THRUST', 'THRUST_QUOTIENT']

for col in h_cols:
    hidden_count = (predict_vt[col].astype(str) == 'HIDDEN').sum()
    if hidden_count > 0:
        print(f"\n{col}:")
        print(f"  HIDDEN 筆數: {hidden_count}")
        sample_rows = predict_vt[predict_vt[col].astype(str) == 'HIDDEN'].head(2)
        for idx, row in sample_rows.iterrows():
            print(f"    例: {row['De-identification Name']} Day {row['NOON_UTC']} -> HIDDEN (無法用)")

print("\n\n" + "="*80)
print("對應關係")
print("="*80)

print("""
訓練船 (S1-S12):
  ✓ 所有欄位都有實際數值
  ✓ 油耗值：有數字（可用於訓練標籤）
  ✓ 主機性能：有數字（可用於訓練特徵）

預測船養護前 (S21-S23 非 PREDICT):
  ✗ 油耗值：空值或其他值（無標籤，但可用於驗證）
  ✗ 主機性能：HIDDEN（無法用作特徵）
  ✓ 環境/航行特徵：有數字（可用）

預測船養護後 (S21-S23 PREDICT):
  ✗ 油耗值：PREDICT（需要你預測！）
  ✗ 主機性能：HIDDEN（無法用作特徵）
  ✓ 環境/航行特徵：有數字（用於做預測）
""")

print("\n" + "="*80)
print("預測流程")
print("="*80)

print("""
輸入 (模型可看的):
  ✓ 環境特徵：WIND_SPEED, SEA_HEIGHT, WATER_DEPTH, TEMP...
  ✓ 航行特徵：AVG_SPEED, ME_AVG_RPM, CARGO_ON_BOARD...
  ✓ 時間特徵：DAYS_SINCE_LAST_MAINT, MAINT_TYPE_*...
  ✗ 主機特徵：全是 HIDDEN（看不到）

預測目標:
  ▶ 對這 102 行「PREDICT」預測油耗值

輸出 (提交格式):
  ship_id, day, fuel_type, predicted_value
  S21, 1383, ME_FULLSPEED_CONSUMP_HSHFO, XX.X
  ... (共 102 行)
""")

print("\n" + "="*80)
print("所以...")
print("="*80)

print("""
HIDDEN = 無法用的特徵資訊（不是預測對象）
PREDICT = 需要預測的油耗值（就是 102 筆）

你只需要預測 102 個 PREDICT
""")
