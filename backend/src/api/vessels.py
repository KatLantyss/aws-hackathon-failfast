"""
船舶相關 API 端點
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import pandas as pd
from utils.s3_client import s3_client
from utils.dynamodb_client import dynamodb_client
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


@router.get("/vessels")
async def list_vessels():
    """
    取得所有船舶列表
    """
    try:
        # 檢查快取
        cache_key = "vessels_list"
        cached = dynamodb_client.get_api_cache(cache_key)
        if cached:
            logger.info("Returning cached vessels list")
            return cached
        
        # 從 S3 讀取數據
        df = s3_client.load_voyage_data()
        
        # 提取船舶資訊
        vessels = []
        for vessel_id in df["De-identification Name"].unique():
            vessel_df = df[df["De-identification Name"] == vessel_id]
            
            # 計算摘要資訊
            latest = vessel_df.iloc[-1]
            vessels.append({
                "vessel_id": vessel_id,
                "vessel_type": "W1" if vessel_id in ["S1","S2","S3","S4","S5","S6","S7","S8","S21"] else "W2",
                "total_days": int(vessel_df["NOON_UTC"].max()),
                "total_voyages": int(vessel_df["VOYAGE"].nunique()),
                "latest_day": int(latest["NOON_UTC"]),
                "latest_speed": float(latest["AVG_SPEED"]) if pd.notna(latest["AVG_SPEED"]) else None,
                "latest_displacement": float(latest["DISPLACEMENT"]) if pd.notna(latest["DISPLACEMENT"]) else None,
            })
        
        result = {
            "total": len(vessels),
            "vessels": sorted(vessels, key=lambda x: x["vessel_id"])
        }
        
        # 快取結果
        dynamodb_client.put_api_cache(cache_key, result, ttl_seconds=3600)
        
        return result
    
    except Exception as e:
        logger.error(f"Error listing vessels: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vessels/{vessel_id}")
async def get_vessel_detail(vessel_id: str):
    """
    取得船舶詳細資訊
    """
    try:
        cache_key = f"vessel_detail_{vessel_id}"
        cached = dynamodb_client.get_api_cache(cache_key)
        if cached:
            return cached
        
        df = s3_client.load_voyage_data()
        vessel_df = df[df["De-identification Name"] == vessel_id]
        
        if vessel_df.empty:
            raise HTTPException(status_code=404, detail=f"Vessel {vessel_id} not found")
        
        # 計算統計資訊
        result = {
            "vessel_id": vessel_id,
            "vessel_type": "W1" if vessel_id in ["S1","S2","S3","S4","S5","S6","S7","S8","S21"] else "W2",
            "statistics": {
                "total_days": int(vessel_df["NOON_UTC"].max()),
                "total_records": len(vessel_df),
                "avg_speed": float(vessel_df["AVG_SPEED"].mean()),
                "avg_displacement": float(vessel_df["DISPLACEMENT"].mean()),
                "avg_wind_scale": float(vessel_df["WIND_SCALE"].mean()),
            },
            "latest_status": {
                "day": int(vessel_df.iloc[-1]["NOON_UTC"]),
                "speed": float(vessel_df.iloc[-1]["AVG_SPEED"]),
                "rpm": float(vessel_df.iloc[-1]["ME_AVG_RPM"]),
                "displacement": float(vessel_df.iloc[-1]["DISPLACEMENT"]),
            }
        }
        
        dynamodb_client.put_api_cache(cache_key, result, ttl_seconds=1800)
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting vessel detail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vessels/{vessel_id}/noon-reports")
async def get_noon_reports(
    vessel_id: str,
    start_day: Optional[int] = Query(None, description="起始天數"),
    end_day: Optional[int] = Query(None, description="結束天數"),
    limit: int = Query(100, ge=1, le=1000, description="最多回傳筆數")
):
    """
    取得船舶航行日報數據
    """
    try:
        df = s3_client.load_voyage_data()
        vessel_df = df[df["De-identification Name"] == vessel_id].copy()
        
        if vessel_df.empty:
            raise HTTPException(status_code=404, detail=f"Vessel {vessel_id} not found")
        
        # 篩選日期範圍
        if start_day is not None:
            vessel_df = vessel_df[vessel_df["NOON_UTC"] >= start_day]
        if end_day is not None:
            vessel_df = vessel_df[vessel_df["NOON_UTC"] <= end_day]
        
        # 限制筆數
        vessel_df = vessel_df.head(limit)
        
        # 轉換為 JSON
        records = vessel_df.to_dict(orient='records')
        
        # 清理 NaN 值
        for record in records:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None
        
        return {
            "vessel_id": vessel_id,
            "total": len(records),
            "records": records
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting noon reports: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
