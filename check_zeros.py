import pandas as pd

sl = pd.read_csv('speed_loss_simple.csv')
print(f'Total: {len(sl)}')
print(f'Exact 0: {(sl["speed_loss_pct"] == 0).sum()}')
print(f'Distribution:')
print(f'  < 0: {(sl["speed_loss_pct"] < 0).sum()}')
print(f'  0-10: {((sl["speed_loss_pct"] >= 0) & (sl["speed_loss_pct"] < 10)).sum()}')
print(f'  10-20: {((sl["speed_loss_pct"] >= 10) & (sl["speed_loss_pct"] < 20)).sum()}')
print(f'  20-50: {((sl["speed_loss_pct"] >= 20) & (sl["speed_loss_pct"] < 50)).sum()}')
print(f'  >= 50: {(sl["speed_loss_pct"] >= 50).sum()}')
