#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert Speed Loss CSV files to JSON format for frontend dashboard
"""
import csv
import json
import os
import sys
from collections import defaultdict

# Force UTF-8 output
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def csv_to_json():
    """Convert CSV files to JSON structure"""
    backend_dir = os.path.dirname(os.path.abspath(__file__))

    # Read summary
    summary_data = {}
    with open(os.path.join(backend_dir, 'speed_loss_summary.csv'), 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ship_id = row['ship']
            summary_data[ship_id] = {
                'avg_sl_pct': float(row['avg_sl_pct']),
                'median_sl': float(row['median_sl']),
                'p10': float(row['p10']),
                'p25': float(row['p25']),
                'p75': float(row['p75']),
                'p90': float(row['p90']),
                'max_sl': float(row['max_sl']),
                'negative_pct': float(row['negative_pct']),
                'cycles': int(row['cycles'])
            }

    # Read timeline
    timeline_data = defaultdict(list)
    with open(os.path.join(backend_dir, 'speed_loss_timeline.csv'), 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ship_id = row['ship']
            timeline_data[ship_id].append({
                'day': int(float(row['noon_day'])) if row['noon_day'] != '' else None,
                'rpm': float(row['rpm']) if row['rpm'] != '' else None,
                'stw': float(row['stw']) if row['stw'] != '' else None,
                'speed_loss_pct': float(row['speed_loss_pct']) if row['speed_loss_pct'] != '' else None,
                'wind_scale': float(row['wind_scale']) if row['wind_scale'] != '' else None,
                'foc': float(row['daily_foc_vlsfo']) if row['daily_foc_vlsfo'] != '' else None
            })

    # Read maintenance impact
    maintenance_data = []
    with open(os.path.join(backend_dir, 'speed_loss_maintenance_impact.csv'), 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                maintenance_data.append({
                    'ship_id': row['ship'],
                    'event_day': int(float(row['event_day'])) if row['event_day'] != '' else None,
                    'event_type': row['event_type'],
                    'sl_before_30d': float(row['sl_before_30d']) if row['sl_before_30d'] != '' else None,
                    'sl_after_30d': float(row['sl_after_30d']) if row['sl_after_30d'] != '' else None,
                    'sl_drop': float(row['sl_drop']) if row['sl_drop'] != '' else None,
                    'foc_before_30d': float(row['foc_before_30d']) if row['foc_before_30d'] != '' else None,
                    'foc_after_30d': float(row['foc_after_30d']) if row['foc_after_30d'] != '' else None,
                    'foc_drop_pct': float(row['foc_drop_pct']) if row['foc_drop_pct'] != '' else None,
                    'rpm_before_avg': float(row['rpm_before_avg']) if row['rpm_before_avg'] != '' else None,
                    'rpm_after_avg': float(row['rpm_after_avg']) if row['rpm_after_avg'] != '' else None,
                    'rpm_normalized_foc_drop_pct': float(row['rpm_normalized_foc_drop_pct']) if row['rpm_normalized_foc_drop_pct'] != '' else None
                })
            except ValueError:
                continue

    # Build fleet summary
    all_ships = sorted(summary_data.keys())
    avg_fleet_sl = sum(v['avg_sl_pct'] for v in summary_data.values()) / len(summary_data) if summary_data else 0
    best_ship = min(summary_data.items(), key=lambda x: x[1]['avg_sl_pct'])[0]
    worst_ship = max(summary_data.items(), key=lambda x: x[1]['avg_sl_pct'])[0]

    # Create final JSON structure
    output = {
        'method': 'STW-based percentile (ISO 19030 Layer 1)',
        'baseline_type': 'top 10% STW per RPM range',
        'fleet_summary': {
            'total_ships': len(all_ships),
            'avg_fleet_speed_loss': round(avg_fleet_sl, 2),
            'best_ship': best_ship,
            'best_ship_sl': round(summary_data[best_ship]['avg_sl_pct'], 2),
            'worst_ship': worst_ship,
            'worst_ship_sl': round(summary_data[worst_ship]['avg_sl_pct'], 2),
            'all_ships': all_ships
        },
        'ship_stats': summary_data,
        'timeseries': {ship: sorted(data, key=lambda x: x['day']) for ship, data in timeline_data.items()},
        'maintenance_events': maintenance_data
    }

    # Write JSON
    output_path = os.path.join(backend_dir, '..', 'frontend', 'public', 'data', 'visualization_data.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✅ 已生成 JSON: {output_path}")
    print(f"   - {len(all_ships)} 艘船")
    print(f"   - 船隊平均 Speed Loss: {avg_fleet_sl:.2f}%")
    print(f"   - 最佳: {best_ship} ({summary_data[best_ship]['avg_sl_pct']:.2f}%)")
    print(f"   - 最差: {worst_ship} ({summary_data[worst_ship]['avg_sl_pct']:.2f}%)")
    print(f"   - {len(maintenance_data)} 個維修事件")

if __name__ == '__main__':
    csv_to_json()
