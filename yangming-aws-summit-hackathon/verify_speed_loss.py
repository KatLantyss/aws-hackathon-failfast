"""
驗證 Speed Loss 計算的準確性
"""
import pandas as pd
import numpy as np

print("="*70)
print("Speed Loss Calculation Verification Report")
print("="*70)

# Load complete data
df = pd.read_csv('speed_loss_output/speed_loss_complete.csv', low_memory=False)

print("\n[DATA OVERVIEW]")
print(f"Total records: {len(df):,}")
print(f"Number of vessels: {df['ship_id'].nunique()}")
print(f"Time range: Day {df['NOON_UTC'].min():.0f} - Day {df['NOON_UTC'].max():.0f}")

print("\n[FUEL CONSUMPTION STATS] (Daily FOC, MT/day)")
print(f"Average: {df['daily_foc'].mean():.2f}")
print(f"Min: {df['daily_foc'].min():.2f}")
print(f"Max: {df['daily_foc'].max():.2f}")
print(f"Std Dev: {df['daily_foc'].std():.2f}")

print("\n[SPEED LOSS STATISTICS]")
print("\nLayer 1 (Baseline Method):")
print(f"  Average: {df['speed_loss_pct_l1'].mean():.2f}%")
print(f"  Median: {df['speed_loss_pct_l1'].median():.2f}%")
print(f"  Min: {df['speed_loss_pct_l1'].min():.2f}%")
print(f"  Max: {df['speed_loss_pct_l1'].max():.2f}%")
print(f"  Valid: {df['speed_loss_pct_l1'].notna().sum():,}")

print("\nLayer 2 (Multi-factor Model):")
print(f"  Average: {df['speed_loss_pct_l2'].mean():.2f}%")
print(f"  Median: {df['speed_loss_pct_l2'].median():.2f}%")
print(f"  Valid: {df['speed_loss_pct_l2'].notna().sum():,}")

print("\n[VESSEL PERFORMANCE ANALYSIS]")
stats = pd.read_csv('speed_loss_output/fleet_statistics.csv')
stats_sorted = stats.sort_values('avg_speed_loss_l1')

print("\nBest Performers (Top 3):")
for idx, row in stats_sorted.head(3).iterrows():
    print(f"  {row['ship_id']:3} - Speed Loss: {row['avg_speed_loss_l1']:6.1f}%, "
          f"Avg FOC: {row['avg_foc']:6.2f} MT/day, Days: {row['days_count']:.0f}")

print("\nNeeds Improvement (Bottom 3):")
for idx, row in stats_sorted.tail(3).iterrows():
    print(f"  {row['ship_id']:3} - Speed Loss: {row['avg_speed_loss_l1']:6.1f}%, "
          f"Avg FOC: {row['avg_foc']:6.2f} MT/day, Days: {row['days_count']:.0f}")

print("\n[MAINTENANCE BENEFIT VERIFICATION]")
maintenance_df = df.dropna(subset=['maintenance_improvement_pct'])
if len(maintenance_df) > 0:
    print(f"Recorded maintenance events: {len(maintenance_df)}")
    print(f"Average improvement: {maintenance_df['maintenance_improvement_pct'].mean():.2f}%")
    print(f"Max improvement: {maintenance_df['maintenance_improvement_pct'].max():.2f}%")
    print(f"Min improvement: {maintenance_df['maintenance_improvement_pct'].min():.2f}%")
else:
    print("No maintenance benefit records")

print("\n[ANOMALY EVENT STATISTICS]")
anomalies = pd.read_csv('speed_loss_output/anomalies.csv')
print(f"Total anomaly events: {len(anomalies)}")
print(f"High speed loss events: {len(anomalies[anomalies['type'] == 'HIGH_SPEED_LOSS'])}")
print(f"Abnormal FOC events: {len(anomalies[anomalies['type'] == 'ABNORMAL_FOC'])}")
print(f"HIGH severity: {len(anomalies[anomalies['severity'] == 'HIGH'])}")
print(f"MEDIUM severity: {len(anomalies[anomalies['severity'] == 'MEDIUM'])}")

print("\n" + "="*70)
print("Verification Complete")
print("="*70)
