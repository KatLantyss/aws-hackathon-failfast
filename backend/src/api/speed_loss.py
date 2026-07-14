"""
Speed Loss 相關 API 端點
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
from utils.s3_client import s3_client
from utils.dynamodb_client import dynamodb_client
from utils.logger import setup_logger
from ml.speed_loss_calculator import SpeedLossCalculator

logger = setup_logger(__name__)
router = APIRouter()


@router.get("/vessels/{vessel_id}/speed-loss")
async def get_speed_loss(vessel_id: str):
    """
    計算並回傳船舶的 Speed Loss 時間序列（ISO 19030）
    """
    try:
        # 檢查快取
        cache_key = f"speed_loss_{vessel_id}"
        cached = dynamodb_client.get_api_cache(cache_key)
        if cached:
            logger.info(f"Returning cached speed loss for {vessel_id}")
            return cached
        
        # 載入數據
        df = s3_client.load_voyage_data()
        vessel_df = df[df["De-identification Name"] == vessel_id].copy()
        
        if vessel_df.empty:
            raise HTTPException(status_code=404, detail=f"Vessel {vessel_id} not found")
        
        # 載入維護事件
        maintenance_df = s3_client.load_maintenance_data()
        vessel_maintenance = maintenance_df[maintenance_df["ship_id"] == vessel_id]
        
        # 計算 Speed Loss
        calculator = SpeedLossCalculator()
        speed_loss_series = calculator.calculate_speed_loss(vessel_df, vessel_maintenance)
        
        # 格式化輸出
        result = {
            "vessel_id": vessel_id,
            "vessel_type": "W1" if vessel_id in ["S1","S2","S3","S4","S5","S6","S7","S8","S21"] else "W2",
            "baseline": {
                "source": speed_loss_series.get("baseline_info", "First clean period"),
                "reference_speed_kt": float(speed_loss_series.get("baseline_speed", 18.5)),
            },
            "series": speed_loss_series["data"],
            "summary": {
                "current_speed_loss_pct": float(speed_loss_series["data"][-1]["speed_loss_pct"]) if speed_loss_series["data"] else 0,
                "avg_speed_loss_pct": float(np.mean([d["speed_loss_pct"] for d in speed_loss_series["data"]])),
                "max_speed_loss_pct": float(max([d["speed_loss_pct"] for d in speed_loss_series["data"]])) if speed_loss_series["data"] else 0,
            }
        }
        
        # 快取結果（1小時）
        dynamodb_client.put_api_cache(cache_key, result, ttl_seconds=3600)
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating speed loss: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vessels/{vessel_id}/speed-loss-attribution")
async def get_speed_loss_attribution(vessel_id: str):
    """
    Speed Loss 歸因分析（船殼 vs 螺旋槳）
    """
    try:
        cache_key = f"speed_loss_attribution_{vessel_id}"
        cached = dynamodb_client.get_api_cache(cache_key)
        if cached:
            return cached
        
        # 載入數據
        maintenance_df = s3_client.load_maintenance_data()
        vessel_maintenance = maintenance_df[maintenance_df["ship_id"] == vessel_id]
        
        if vessel_maintenance.empty:
            raise HTTPException(status_code=404, detail=f"No maintenance data for {vessel_id}")
        
        # 計算歸因（簡化版本）
        calculator = SpeedLossCalculator()
        attribution = calculator.calculate_attribution(vessel_id, vessel_maintenance)
        
        result = {
            "vessel_id": vessel_id,
            "attribution": attribution,
            "method": "differential_analysis",
            "confidence": "medium"
        }
        
        dynamodb_client.put_api_cache(cache_key, result, ttl_seconds=7200)
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating attribution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
