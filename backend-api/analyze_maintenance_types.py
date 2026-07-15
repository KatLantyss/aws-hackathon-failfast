import pandas as pd

csv = pd.read_csv(r'C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\speed_loss_maintenance_impact.csv')
csv['sl_drop'] = pd.to_numeric(csv['sl_drop'], errors='coerce')
valid = csv[csv['sl_drop'].notna()]

print("=" * 70)
print("Maintenance type effectiveness analysis")
print("=" * 70)

for mtype in ['DD', 'UWC+PP', 'UWC', 'PP', 'UWI+PP', 'UWI']:
    group = valid[valid['event_type'] == mtype]
    if len(group) == 0:
        continue

    improved = (group['sl_drop'] > 0).sum()
    total = len(group)
    avg_drop = group['sl_drop'].mean()
    improvement_rate = improved / total * 100

    print(f"{mtype:8s}: {improved:2d}/{total:2d} ({improvement_rate:5.1f}%) | avg_drop={avg_drop:6.2f}%")

print("=" * 70)
print("\nExpected hierarchy (from most to least effective):")
print("  DD        > 80%")
print("  UWC+PP    > 60%")
print("  UWC       > 40%")
print("  PP        > 20%")
print("  UWI+PP    > 15%")
print("  UWI       ~ 0% (no intervention, just inspection)")
