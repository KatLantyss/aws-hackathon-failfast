import pandas as pd
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)

# 只看預測船
predict_ships = ['S21', 'S22', 'S23']
predict_vt = vt[vt['De-identification Name'].isin(predict_ships)]

# 檢查各欄位
predict_cols = ['ME_FULLSPEED_CONSUMP_HSHFO', 'ME_FULLSPEED_CONSUMP_VLSFO',
                'ME_FULLSPEED_CONSUMP_ULSFO', 'ME_FULLSPEED_CONSUMP_LSMGO']
h_cols = ['HORSE_POWER', 'LOAD_PCT', 'SFOC', 'ME_SLIP', 'THRUST', 'THRUST_QUOTIENT']

print("="*80)
print("MASK 統計 (被遮蔽欄位)")
print("="*80)

# 統計 PREDICT
print("\n[PREDICT] 需要預測的值:")
predict_count = 0
for col in predict_cols:
    predict_in_col = (predict_vt[col].astype(str) == 'PREDICT').sum()
    predict_count += predict_in_col
    if predict_in_col > 0:
        print(f"  {col}: {predict_in_col}")

print(f"\n總 PREDICT 標記: {predict_count} 筆")

# 統計 HIDDEN
print("\n[HIDDEN] 存在但不提供的值:")
hidden_count = 0
for col in h_cols:
    hidden_in_col = (predict_vt[col].astype(str) == 'HIDDEN').sum()
    hidden_count += hidden_in_col
    if hidden_in_col > 0:
        print(f"  {col}: {hidden_in_col}")

if hidden_count == 0:
    print("  (無 HIDDEN 標記 - 這些欄位在預測期間完全可見)")
else:
    print(f"\n總 HIDDEN 標記: {hidden_count}")

print("\n" + "="*80)
print("預測船分佈")
print("="*80)
print(f"\n預測船總行數: {len(predict_vt)}")
for ship in predict_ships:
    ship_rows = len(predict_vt[predict_vt['De-identification Name'] == ship])
    print(f"  {ship}: {ship_rows} 行")

print("\n" + "="*80)
print("評分標準")
print("="*80)
print(f"""
PREDICT 筆數: {predict_count}

這應該是評分標準 - 每個 PREDICT 標記都對應一個需要提交的預測值
（見 README：共 102 個 PREDICT，14 個事件，每事件 5-10 天）
""")

# 檢查每艘船的 PREDICT 分佈
print("\nPREDICT 在各船的分佈:")
for ship in predict_ships:
    ship_data = predict_vt[predict_vt['De-identification Name'] == ship]
    count = 0
    for col in predict_cols:
        count += (ship_data[col].astype(str) == 'PREDICT').sum()
    if count > 0:
        print(f"  {ship}: {count}")
