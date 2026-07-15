"""
測試維修效能分析API端點
"""
import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'backend-api'))

import json
import handler

# 測試 S1 的維修效能分析
print("Testing maintenance-correlation API...\n")

event = {
    'httpMethod': 'GET',
    'path': '/api/v1/vessels/S1/maintenance-correlation',
}

result = handler.route(event, None)
print(f"Status: {result['statusCode']}")

if result['statusCode'] == 200:
    data = json.loads(result['body'])
    print(f"\nVessel: {data['vessel']['imo']}")
    print(f"Timeline points: {len(data['timeline'])}")
    print(f"Maintenance events: {len(data['events'])}")
    print(f"Maintenance types: {len(data['typeEffectiveness'])}")
    print(f"\nSummary:")
    print(f"  Total events: {data['summary']['totalEvents']}")
    print(f"  Avg improvement: {data['summary']['avgImprovementPct']:.1f}%")
    print(f"  Total fuel saved: {data['summary']['totalFuelSavedMt']:.1f} MT")
    print(f"  Total cost: ${data['summary']['totalMaintenanceCostUsd']:,}")

    print(f"\nOptimal timing:")
    print(f"  Current Speed Loss: {data['optimalTiming']['currentSpeedLossPct']:.1f}%")
    print(f"  Urgency: {data['optimalTiming']['urgency']}")
    print(f"  Recommended: {data['optimalTiming']['recommendedAction']}")

    print(f"\nType effectiveness:")
    for t in data['typeEffectiveness']:
        print(f"  {t['type']}: {t['avgImprovementPct']:.1f}% improvement, n={t['eventCount']}")
else:
    print(f"Error: {result['body']}")
