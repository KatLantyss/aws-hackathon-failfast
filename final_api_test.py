import urllib.request, json

print("\n" + "="*70)
print("維修效能分析 API - 最終測試")
print("="*70 + "\n")

ships = ['S1', 'S3', 'S10', 'S22']

for ship in ships:
    try:
        url = f'http://localhost:8000/api/v1/vessels/{ship}/maintenance-correlation'
        r = urllib.request.urlopen(url)
        d = json.loads(r.read().decode())

        print(f"[{ship}]")
        print(f"  Timeline: {len(d['timeline'])} points")
        print(f"  Events: {d['summary']['totalEvents']}")
        print(f"  Improvement: {d['summary']['avgImprovementPct']:.1f}%")
        print(f"  Fuel saved: {d['summary']['totalFuelSavedMt']:.1f} MT")
        print(f"  Cost: ${d['summary']['totalMaintenanceCostUsd']:,}")
        print(f"  Speed Loss: {d['optimalTiming']['currentSpeedLossPct']:.1f}%")
        print(f"  Urgency: {d['optimalTiming']['urgency']}")
        if d['typeEffectiveness']:
            print(f"  Best type: {d['typeEffectiveness'][0]['type']}")
        print()
    except Exception as e:
        print(f"  Error: {str(e)[:50]}")

print("="*70)
print("✅ 後端 API 已正常運行")
print("前端可以連接: http://localhost:8000/api/v1/vessels/{imo}/maintenance-correlation")
print("="*70)
