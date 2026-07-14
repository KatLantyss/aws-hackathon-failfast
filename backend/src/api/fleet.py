"""
船隊相關 API 端點
"""
from fastapi import APIRouter, HTTPException
from typing import List
import pandas as pd
from utils.s3_client import s3_client
from utils.dynamodb_client import dynamodb_client
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


@router.get("/fleet/ranking")
async def get_fleet_ranking():
    """
    船隊排名（依 Speed Loss、油耗效率）
    """
    try:
        cache_key = "fleet_ranking"
        cached = dynamodb_client.get_api_cache(cache_key)
        if cached:
            return cached
        
        df = s3_client.load_voyage_data()
        
        # 計算各船當前狀態（簡化版）
        rankings = []
        for vessel_id in df["De-identification Name"].unique():
            vessel_df = df[df["De-identification Name"] == vessel_id]
            latest = vessel_df.iloc[-1]
            
            rankings.append({
                "vessel_id": vessel_id,
                "estimated_speed_loss_pct": 3.5,  # 實際應從計算獲得
                "avg_fuel_consumption": float(vessel_df["ME_CONSUMPTION"].mean()) if "ME_CONSUMPTION" in vessel_df.columns else None,
                "priority": "medium"
            })
        
        # 排序
        rankings.sort(key=lambda x: x["estimated_speed_loss_pct"], reverse=True)
        
        result = {
            "total": len(rankings),
            "rankings": rankings
        }
        
        dynamodb_client.put_api_cache(cache_key, result, ttl_seconds=1800)
        return result
    
    except Exception as e:
        logger.error(f"Error getting fleet ranking: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
