"""
船舶效能分析 API - FastAPI 應用主程式
支援 AWS Lambda (Mangum) 部署
"""
import os
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

# 自定義模組
from api.vessels import router as vessels_router
from api.speed_loss import router as speed_loss_router
from api.predictions import router as predictions_router
from api.maintenance import router as maintenance_router
from api.fleet import router as fleet_router
from utils.config import settings
from utils.logger import setup_logger

# 設定日誌
logger = setup_logger(__name__)

# 建立 FastAPI 應用
app = FastAPI(
    title="Ship Performance Analysis API",
    description="陽明海運 AI 黑客松 - 船舶效能分析與節能決策支援系統",
    version="1.0.0",
    docs_url="/api/docs" if settings.ENVIRONMENT != "prod" else None,
    redoc_url="/api/redoc" if settings.ENVIRONMENT != "prod" else None,
)

# CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生產環境應限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)

# 健康檢查端點
@app.get("/health")
@app.get("/api/health")
async def health_check():
    """健康檢查"""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0",
        "model_version": os.getenv("MODEL_VERSION", "unknown")
    }

# 根路徑
@app.get("/")
async def root():
    """API 根路徑"""
    return {
        "message": "Ship Performance Analysis API",
        "version": "1.0.0",
        "docs": "/api/docs",
        "health": "/health"
    }

# 註冊路由
app.include_router(vessels_router, prefix="/api/v1", tags=["Vessels"])
app.include_router(speed_loss_router, prefix="/api/v1", tags=["Speed Loss"])
app.include_router(predictions_router, prefix="/api/v1", tags=["Predictions"])
app.include_router(maintenance_router, prefix="/api/v1", tags=["Maintenance"])
app.include_router(fleet_router, prefix="/api/v1", tags=["Fleet"])

# 全域錯誤處理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全域錯誤處理"""
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.ENVIRONMENT != "prod" else "An error occurred"
        }
    )

# Lambda Handler
handler = Mangum(app, lifespan="off")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
