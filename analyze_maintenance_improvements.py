#!/usr/bin/env python3
"""
Analyze maintenance effectiveness distribution across event types
to determine reasonable anomaly thresholds.
"""
import json
import boto3
from collections import defaultdict
from statistics import mean, median, stdev

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('ship-analysis-dev-maintenance-events')

# Fetch all maintenance records
def fetch_all_maintenance():
    events_by_type = defaultdict(list)

    # Scan the table (limit to 1000 for now)
    response = table.scan(Limit=1000)
    items = response.get('Items', [])

    while 'LastEvaluatedKey' in response:
        response = table.scan(
            Limit=1000,
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        items.extend(response.get('Items', []))

    print(f"Total maintenance records fetched: {len(items)}")

    # Group by event type and calculate improvements
    for item in items:
        event_type = item.get('event_type', 'unknown')

        # Calculate RPM-normalized improvement
        fuel_before = float(item.get('fuel_before_30day_avg', 0))
        fuel_after = float(item.get('fuel_after_30day_avg', 0))
        rpm_before = float(item.get('rpm_before_30day_avg', 1))  # avoid div by 0
        rpm_after = float(item.get('rpm_after_30day_avg', 1))

        if fuel_before > 0 and rpm_before > 0:
            # Normalize: (fuel/rpm)_before vs (fuel/rpm)_after
            sfc_before = fuel_before / rpm_before
            sfc_after = fuel_after / rpm_after

            if sfc_before > 0:
                rpm_normalized_improvement = ((sfc_before - sfc_after) / sfc_before) * 100
                events_by_type[event_type].append({
                    'day': item.get('event_day'),
                    'fuel_improvement': ((fuel_before - fuel_after) / fuel_before) * 100,
                    'rpm_normalized_improvement': rpm_normalized_improvement,
                })

    return events_by_type

# Analyze and print statistics
def print_stats(events_by_type):
    print("\n" + "="*80)
    print("MAINTENANCE EFFECTIVENESS ANALYSIS")
    print("="*80)

    for event_type in sorted(events_by_type.keys()):
        improvements = [e['rpm_normalized_improvement'] for e in events_by_type[event_type]]

        if not improvements:
            continue

        count = len(improvements)
        avg = mean(improvements)
        med = median(improvements)
        std = stdev(improvements) if count > 1 else 0
        min_val = min(improvements)
        max_val = max(improvements)

        print(f"\n{event_type} ({count} records):")
        print(f"  RPM-Normalized Improvement % :")
        print(f"    Mean:    {avg:7.2f}%")
        print(f"    Median:  {med:7.2f}%")
        print(f"    StdDev:  {std:7.2f}%")
        print(f"    Range:   {min_val:7.2f}% → {max_val:7.2f}%")
        print(f"    P25:     {sorted(improvements)[int(count*0.25)]:7.2f}%")
        print(f"    P75:     {sorted(improvements)[int(count*0.75)]:7.2f}%")

        # Suggest thresholds
        p25 = sorted(improvements)[int(count*0.25)]
        p75 = sorted(improvements)[int(count*0.75)]

        print(f"\n  ⚡ Suggested anomaly threshold:")
        print(f"    Normal range: {p25:.1f}% - {p75:.1f}%")
        print(f"    Anomaly if:  < {p25:.1f}% OR > {p75:.1f}%")

if __name__ == '__main__':
    events_by_type = fetch_all_maintenance()
    print_stats(events_by_type)
