"""
簡單測試：直接啟動 FastAPI 應用
"""
import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'backend-api'))

from fastapi import FastAPI
import handler
import json
from fastapi.responses import JSONResponse

app = FastAPI(title="Test API", version="1.0.0")

@app.get("/api/v1/vessels/{vessel_id}/maintenance-correlation")
def get_maintenance_correlation(vessel_id: str):
    """Test endpoint"""
    event = {
        'httpMethod': 'GET',
        'path': f'/api/v1/vessels/{vessel_id}/maintenance-correlation',
    }
    result = handler.route(event, None)
    return JSONResponse(
        content=json.loads(result["body"]),
        status_code=result["statusCode"],
    )

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*70)
    print("啟動測試 API 服務器...")
    print("訪問: http://localhost:8000/api/v1/vessels/S1/maintenance-correlation")
    print("="*70 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
