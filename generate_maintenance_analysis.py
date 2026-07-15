"""
生成維修效能分析 JSON - 用於前端 MaintenanceCorrelation.vue
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("\n" + "="*80)
print("維修效能分析 JSON 生成")
print("="*80)

# ============================================================================
# Load data
# ============================================================================
print("\n[Loading data...]")

vt = pd.read_csv('yangming-aws-summit-hackathon/vt_fd.csv', low_memory=False)
maint = pd.read_csv('yangming-aws-summit-hackathon/maintenance.csv', low_memory=False)
sl = pd.read_csv('speed_loss_simple.csv')

vt = vt.rename(columns={'De-identification Name': 'ship_id'})

for col in ['NOON_UTC', 'TOTAL_CONSUMP', 'WIND_SCALE', 'HOURS_FULL_SPEED']:
    if col in vt.columns:
        vt[col] = pd.to_numeric(vt[col], errors='coerce')

maint['event_day'] = pd.to_numeric(maint['event_day'], errors='coerce')
sl['NOON_UTC'] = pd.to_numeric(sl['NOON_UTC'], errors='coerce')
sl['speed_loss_pct'] = pd.to_numeric(sl['speed_loss_pct'], errors='coerce')

# Base date for day conversion
BASE_DATE = datetime(2020, 1, 1)

def day_to_date(day):
    """Convert day number to YYYY-MM-DD string"""
    d = BASE_DATE + timedelta(days=int(day))
    return d.strftime('%Y-%m-%d')

# Event type mapping
EVENT_TYPE_MAP = {
    'DD': 'Drydock',
    'UWC+PP': 'Hull Cleaning + PP',
    'UWC': 'Hull Cleaning',
    'UWI+PP': 'Propeller Polishing',
    'PP': 'Propeller Polishing',
    'UWI': 'Propeller Polishing',
}

COST_EST = {
    'DD': 500000,
    'UWC+PP': 45000,
    'UWC': 35000,
    'UWI+PP': 25000,
    'PP': 15000,
    'UWI': 8000,
}

print(f"  vt_fd: {len(vt)} rows")
print(f"  maintenance: {len(maint)} rows")
print(f"  speed_loss: {len(sl)} rows")

# ============================================================================
# Generate analysis for each ship
# ============================================================================

results_all = {}
WINDOW_DAYS = 30

for ship_id in sorted(vt['ship_id'].unique()):
    print(f"\n[{ship_id}] Processing...")

    ship_vt = vt[vt['ship_id'] == ship_id].sort_values('NOON_UTC')
    ship_maint = maint[maint['ship_id'] == ship_id].sort_values('event_day')
    ship_sl = sl[sl['ship_id'] == ship_id].sort_values('NOON_UTC')

    if len(ship_maint) == 0:
        print(f"  → No maintenance events, skip")
        continue

    # Timeline: 每3天取1個数据点（油耗+Speed Loss）
    timeline = []
    timeline_days = []  # Keep track of day numbers for window calculation
    for idx in range(0, len(ship_vt), 3):
        row = ship_vt.iloc[idx]
        day = int(row['NOON_UTC'])
        fuel = row['TOTAL_CONSUMP']

        if pd.isna(fuel) or fuel <= 0:
            continue

        # Find speed loss for this day
        sl_match = ship_sl[ship_sl['NOON_UTC'] == day]
        speed_loss = sl_match['speed_loss_pct'].values[0] if len(sl_match) > 0 else 0

        timeline.append({
            'date': day_to_date(day),
            'fuelConsumptionMt': round(float(fuel), 2),
            'speedLossPct': round(float(speed_loss), 2),
        })
        timeline_days.append(day)

    # Events: 计算每个维修前后的效果
    events = []
    for _, maint_row in ship_maint.iterrows():
        event_day = int(maint_row['event_day'])
        event_type = maint_row['event_type']

        # Get fuel data: before/after window
        fuel_before_rows = ship_vt[
            (ship_vt['NOON_UTC'] >= event_day - WINDOW_DAYS) &
            (ship_vt['NOON_UTC'] < event_day) &
            (ship_vt['TOTAL_CONSUMP'] > 10)
        ]
        fuel_after_rows = ship_vt[
            (ship_vt['NOON_UTC'] > event_day) &
            (ship_vt['NOON_UTC'] <= event_day + WINDOW_DAYS) &
            (ship_vt['TOTAL_CONSUMP'] > 10)
        ]

        # Get speed loss: before/after
        sl_before_rows = ship_sl[
            (ship_sl['NOON_UTC'] >= event_day - WINDOW_DAYS) &
            (ship_sl['NOON_UTC'] < event_day)
        ]
        sl_after_rows = ship_sl[
            (ship_sl['NOON_UTC'] > event_day) &
            (ship_sl['NOON_UTC'] <= event_day + WINDOW_DAYS)
        ]

        if len(fuel_before_rows) < 2 or len(fuel_after_rows) < 2:
            continue

        fuel_before = fuel_before_rows['TOTAL_CONSUMP'].mean()
        fuel_after = fuel_after_rows['TOTAL_CONSUMP'].mean()
        fuel_improvement = fuel_before - fuel_after
        improvement_pct = (fuel_improvement / fuel_before * 100) if fuel_before > 0 else 0

        sl_before = sl_before_rows['speed_loss_pct'].mean() if len(sl_before_rows) > 0 else 0
        sl_after = sl_after_rows['speed_loss_pct'].mean() if len(sl_after_rows) > 0 else 0

        # Anomaly detection
        is_anomaly = False
        anomaly_reason = None
        if event_type == 'DD' and improvement_pct < 2:
            is_anomaly = True
            anomaly_reason = '進塢後 Speed Loss 改善不明顯，建議確認塗裝品質。'
        elif event_type == 'PP' and improvement_pct > 15:
            is_anomaly = True
            anomaly_reason = '螺旋槳拋光改善幅度異常高，可能有其他因素。'

        events.append({
            'id': f"{ship_id}-{event_type}-{event_day}",
            'date': day_to_date(event_day),
            'type': EVENT_TYPE_MAP.get(event_type, 'Unknown'),
            'port': '—',
            'fuelBefore': round(fuel_before, 2),
            'fuelAfter': round(fuel_after, 2),
            'fuelImprovementMt': round(fuel_improvement, 2),
            'improvementPct': round(improvement_pct, 1),
            'speedLossBefore': round(float(sl_before), 2),
            'speedLossAfter': round(float(sl_after), 2),
            'costUsd': COST_EST.get(event_type, 30000),
            'isAnomaly': is_anomaly,
            'anomalyReason': anomaly_reason,
        })

    if len(events) == 0:
        print(f"  → No valid maintenance events, skip")
        continue

    # Type effectiveness
    type_map = {}
    for evt in events:
        event_type = evt['type']
        if event_type not in type_map:
            type_map[event_type] = []
        type_map[event_type].append(evt)

    type_effectiveness = []
    for event_type, type_events in type_map.items():
        avg_improvement = np.mean([e['improvementPct'] for e in type_events])
        avg_fuel_improvement = np.mean([e['fuelImprovementMt'] for e in type_events])
        avg_cost = np.mean([e['costUsd'] for e in type_events])
        cost_per_pct = avg_cost / avg_improvement if avg_improvement > 0 else float('inf')

        # Rating
        if avg_improvement >= 10:
            rating = 5
        elif avg_improvement >= 6:
            rating = 4
        elif avg_improvement >= 3:
            rating = 3
        elif avg_improvement >= 1:
            rating = 2
        else:
            rating = 1

        type_effectiveness.append({
            'type': event_type,
            'eventCount': len(type_events),
            'avgImprovementPct': round(avg_improvement, 1),
            'avgFuelImprovementMt': round(avg_fuel_improvement, 2),
            'avgCostUsd': int(round(avg_cost)),
            'costPerPctImprovement': int(round(cost_per_pct)) if cost_per_pct < float('inf') else 0,
            'rating': rating,
        })

    type_effectiveness.sort(key=lambda x: x['avgImprovementPct'], reverse=True)

    # Summary
    total_fuel_saved = sum(max(0, e['fuelImprovementMt']) for e in events)
    total_cost = sum(e['costUsd'] for e in events)
    avg_improvement_pct = np.mean([e['improvementPct'] for e in events])
    anomaly_count = len([e for e in events if e['isAnomaly']])
    best_event = max(events, key=lambda e: e['improvementPct'])
    worst_event = min(events, key=lambda e: e['improvementPct'])

    # Optimal timing
    if len(timeline) > 0:
        current_sl = timeline[-1]['speedLossPct']
        recent_timeline = timeline[-60:] if len(timeline) > 60 else timeline

        if len(recent_timeline) >= 2:
            rate = (recent_timeline[-1]['speedLossPct'] - recent_timeline[0]['speedLossPct']) / len(recent_timeline)
        else:
            rate = 0

        optimal_threshold = 8
        days_until_threshold = max(0, int((optimal_threshold - current_sl) / rate)) if rate > 0 else 90

        # Recommended action
        if current_sl >= 12:
            recommended_action = 'Hull Cleaning + PP'
        elif current_sl < 4:
            recommended_action = 'Propeller Polishing'
        else:
            recommended_action = 'Hull Cleaning'

        # Cost calculation
        baseline_fuel = 155 if ship_id in ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S21'] else 92
        fuel_price = 620
        excess_fuel_cost_per_day = int(baseline_fuel * (max(0, current_sl) / 100) * 1.8 * fuel_price)
        projected_savings = int(baseline_fuel * (
            (type_effectiveness[0]['avgImprovementPct'] if type_effectiveness else 5) / 100
        ) * 1.8 * fuel_price * 90)

        # Urgency
        if current_sl >= 10 or days_until_threshold <= 7:
            urgency = 'HIGH'
        elif current_sl >= 6 or days_until_threshold <= 30:
            urgency = 'MEDIUM'
        else:
            urgency = 'LOW'

        if urgency == 'HIGH':
            reasoning = f"Speed Loss {current_sl:.1f}% 已超過閾值，每日超額成本 ${excess_fuel_cost_per_day:,}。建議立即安排維修。"
        elif urgency == 'MEDIUM':
            reasoning = f"Speed Loss {current_sl:.1f}%，約 {days_until_threshold} 天後達閾值。建議提前安排。"
        else:
            reasoning = f"Speed Loss {current_sl:.1f}% 正常範圍，依標準週期維護。"

        # Use actual day numbers from timeline
        last_day = timeline_days[-1] if timeline_days else 0
        window_start = day_to_date(last_day + days_until_threshold) if timeline else ''
        window_end = day_to_date(last_day + days_until_threshold + 14) if timeline else ''
    else:
        current_sl = 0
        rate = 0
        days_until_threshold = 90
        recommended_action = 'Hull Cleaning'
        excess_fuel_cost_per_day = 0
        projected_savings = 0
        urgency = 'LOW'
        reasoning = 'No data'
        window_start = ''
        window_end = ''

    optimal_timing = {
        'recommendedAction': recommended_action,
        'currentSpeedLossPct': round(current_sl, 1),
        'degradationRatePerDay': round(rate, 4),
        'optimalThresholdPct': 8,
        'daysUntilThreshold': days_until_threshold,
        'windowStart': window_start,
        'windowEnd': window_end,
        'excessFuelCostPerDayUsd': excess_fuel_cost_per_day,
        'projectedSavingsUsd': projected_savings,
        'reasoning': reasoning,
        'urgency': urgency,
    }

    # Assemble response
    response = {
        'vessel': {'imo': ship_id, 'name': ship_id},
        'timeline': timeline,
        'events': events,
        'typeEffectiveness': type_effectiveness,
        'optimalTiming': optimal_timing,
        'summary': {
            'totalEvents': len(events),
            'avgImprovementPct': round(avg_improvement_pct, 1),
            'bestEventId': best_event['id'],
            'worstEventId': worst_event['id'],
            'anomalyCount': anomaly_count,
            'totalMaintenanceCostUsd': int(total_cost),
            'totalFuelSavedMt': round(total_fuel_saved, 1),
        }
    }

    results_all[ship_id] = response
    print(f"  ✓ {len(events)} events, {len(timeline)} timeline points")

# ============================================================================
# Save results
# ============================================================================
print("\n[Saving JSON...]")

with open('maintenance_analysis_json.json', 'w', encoding='utf-8') as f:
    json.dump(results_all, f, ensure_ascii=False, indent=2)

print(f"\n✓ Saved to maintenance_analysis_json.json ({len(results_all)} ships)")

# Summary
print("\n[Summary by ship:]")
for ship_id in sorted(results_all.keys()):
    data = results_all[ship_id]
    print(f"  {ship_id}: {data['summary']['totalEvents']} events, "
          f"avg {data['summary']['avgImprovementPct']:.1f}% improvement, "
          f"${data['summary']['totalMaintenanceCostUsd']:,} cost")

print("\n" + "="*80 + "\n")
