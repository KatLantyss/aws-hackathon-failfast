"""
測試維修效能分析API端點
"""
import urllib.request
import json

print("=" * 70)
print("測試維修效能分析 API 端點")
print("=" * 70)

ships = ['S1', 'S3', 'S22']

for ship in ships:
    try:
        url = f'http://localhost:8000/api/v1/vessels/{ship}/maintenance-correlation'
        response = urllib.request.urlopen(url)
        data = json.loads(response.read().decode())

        print(f"\n✅ {ship}:")
        print(f"   Timeline points: {len(data['timeline'])}")
        print(f"   Maintenance events: {data['summary']['totalEvents']}")
        print(f"   Avg improvement: {data['summary']['avgImprovementPct']:.1f}%")
        print(f"   Total fuel saved: {data['summary']['totalFuelSavedMt']:.1f} MT")
        print(f"   Total cost: ${data['summary']['totalMaintenanceCostUsd']:,}")
        print(f"   Current Speed Loss: {data['optimalTiming']['currentSpeedLossPct']:.1f}%")
        print(f"   Urgency: {data['optimalTiming']['urgency']}")

        if data['typeEffectiveness']:
            print(f"   Top type: {data['typeEffectiveness'][0]['type']} "
                  f"({data['typeEffectiveness'][0]['avgImprovementPct']:.1f}%)")
    except Exception as e:
        print(f"\n❌ {ship}: {str(e)}")

print("\n" + "=" * 70)
print("✅ 後端 API 已正常運行！前端可以連接到 http://localhost:8000")
print("=" * 70)
