import urllib.request
import json

print('='*70)
print('系統驗證 - 維修效能分析')
print('='*70)

# 測試後端API
print('\n[1] 後端 API (localhost:8000)')
try:
    r = urllib.request.urlopen('http://localhost:8000/api/v1/vessels/S1/maintenance-correlation')
    d = json.loads(r.read().decode())
    print('    Status: OK')
    print(f'    Events: {d["summary"]["totalEvents"]}')
    print(f'    Timeline: {len(d["timeline"])} points')
except Exception as e:
    print(f'    Error: {str(e)[:50]}')

# 測試前端
print('\n[2] 前端 (localhost:5173)')
try:
    r = urllib.request.urlopen('http://localhost:5173')
    print('    Status: OK')
    print('    Frontend is running')
except Exception as e:
    print(f'    Error: {str(e)[:50]}')

print('\n' + '='*70)
print('Ready! Open in browser: http://localhost:5173')
print('='*70)
