import pandas as pd
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sl = pd.read_csv('speed_loss_results.csv')

# 過濾極端值
valid = sl[(sl['speed_loss_pct'] > -30) & (sl['speed_loss_pct'] < 50)]
print(f"過濾後: {len(valid)} / {len(sl)} 筆")
print(f"平均 Speed Loss: {valid['speed_loss_pct'].mean():.2f}%")
print(f"中位數: {valid['speed_loss_pct'].median():.2f}%")

# S23 有明顯退化趨勢
print("\nS23 趨勢:")
s23 = valid[valid['ship_id'] == 'S23'].sort_values('NOON_UTC')
for start in range(0, 1900, 200):
    chunk = s23[(s23['NOON_UTC'] >= start) & (s23['NOON_UTC'] < start + 200)]
    if len(chunk) > 0:
        print(f"  Day {start}-{start+200}: avg {chunk['speed_loss_pct'].mean():.1f}%")

# 維修建議
recs = pd.read_csv('maintenance_recommendations.csv')
print(f"\n維修建議: {len(recs)} 筆")
print(recs.groupby('urgency').size())
