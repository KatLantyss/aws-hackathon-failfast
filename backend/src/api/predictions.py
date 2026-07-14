"""
油耗預測相關 API 端點
"""
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Optional
from pydantic import BaseModel, Field
from utils.s3_client import s3_client
from utils.dynamodb_client import dynamodb_client
from utils.logger import setup_logger
from ml.fuel_predictor import FuelPredictor

logger = setup_logger(__name__)
router = APIRouter()


class FuelPredictionRequest(BaseModel):
    """油耗預測請求"""
    vessel_id: str = Field(..., description="船舶代號")
    day: int = Field(..., description="預測天數")
    features: Dict = Field(..., description="航行特徵")
    counterfactual: Optional[Dict] = Field(None, description="反事實模擬參數")


class FuelPredictionResponse(BaseModel):
    """油耗預測回應"""
    vessel_id: str
    day: int
    fuel_type: str
    predicted_value_mt: float
    confidence_interval: Optional[tuple] = None
    counterfactual_result: Optional[Dict] = None


@router.post("/predict/fuel-consumption")
async def predict_fuel_consumption(request: FuelPredictionRequest):
    """
    預測主機全速油耗（支援反事實推論）
    """
    try:
        # 檢查快取
        cache_key = f"prediction_{request.vessel_id}_{request.day}"
        if not request.counterfactual:
            cached = dynamodb_client.get_api_cache(cache_key)
            if cached:
                logger.info(f"Returning cached prediction")
                return cached
        
        # 載入預測模型
        predictor = FuelPredictor()
        
        # 執行預測
        result = predictor.predict(
            vessel_id=request.vessel_id,
            day=request.day,
            features=request.features,
            counterfactual=request.counterfactual
        )
        
        # 快取結果（如果不是反事實）
        if not request.counterfactual:
            dynamodb_client.put_api_cache(cache_key, result, ttl_seconds=7200)
        
        return result
    
    except Exception as e:
        logger.error(f"Error predicting fuel consumption: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict/submit")
async def submit_predictions():
    """
    產出 102 筆預測結果 CSV（評審提交用）
    """
    try:
        predictor = FuelPredictor()
        csv_content = predictor.generate_submission_csv()
        
        return {
            "status": "success",
            "total_predictions": 102,
            "csv_preview": csv_content[:500],
            "download_url": "/api/v1/predict/download"
        }
    
    except Exception as e:
        logger.error(f"Error generating submission: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
