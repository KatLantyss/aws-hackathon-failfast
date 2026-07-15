import pandas as pd
from datetime import timedelta
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)
maint = pd.read_csv('yangming-aws-summit-hackathon/maintenance.csv')

print("=" * 80)
print("時間軸分析")
print("=" * 80)

train_ships = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12']
train_vt = vt[vt['De-identification Name'].isin(train_ships)]

print("\nvt_fd (訓練船):")
print(f"  NOON_UTC 範圍: {train_vt['NOON_UTC'].min():.0f} ~ {train_vt['NOON_UTC'].max():.0f} days")

train_maint = maint[maint['ship_id'].isin(train_ships)]
print(f"\nmaintenance (訓練船):")
print(f"  日期範圍: {train_maint['event_date'].min()} ~ {train_maint['event_date'].max()}")
print(f"  共 {len(train_maint)} 筆")

print("\n" + "=" * 80)
print("🔴 核心問題")
print("=" * 80)
print("""
vt_fd 只有相對天數 (NOON_UTC)：
  - Day 0 = 該船最早紀錄
  - 不知道 Day 0 的絕對日期

maintenance 有絕對日期 (event_date)：
  - 但無法直接與 vt_fd 對齐

需要解決：
  1. 推算每艘船的 Day 0 對應的絕對日期
  2. 或者 maintenance 中是否有其他時間線索？
""")

print("\n檢查 S1 具體數據:")
s1_vt = vt[vt['De-identification Name'] == 'S1']
s1_maint = maint[maint['ship_id'] == 'S1']

print(f"\nvt_fd (S1):")
print(f"  NOON_UTC 範圍: {s1_vt['NOON_UTC'].min():.0f} ~ {s1_vt['NOON_UTC'].max():.0f}")
print(f"  日記行數: {len(s1_vt)}")

print(f"\nmaintenance (S1):")
print(s1_maint[['ship_id', 'event_date', 'event_type']])

print("\n" + "=" * 80)
print("💡 可能的解決方案")
print("=" * 80)
print("""
方案 1：假設維護時間點
  - 假設 maintenance 日期對應某個具體的 NOON_UTC
  - 例如 maintenance 在 NOON_UTC=500，就算 Day 500
  - 但這需要數據一致性假設

方案 2：檢查是否有隱藏的日期信息
  - VOYAGE 欄位是否包含日期線索？
  - 檢查數據是否有其他時間錨點

方案 3：相對匹配
  - 不用絕對日期，只用相對順序
  - 例如：第 N 次養護發生在第 X 行之後

推薦：先檢查 VOYAGE 是否有日期，或者詢問數據提供者
""")

# 檢查 VOYAGE
print("\n檢查 VOYAGE 欄位:")
print(vt[vt['De-identification Name'] == 'S1'][['NOON_UTC', 'VOYAGE']].head(10))
