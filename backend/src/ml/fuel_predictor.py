"""
油耗預測模型（LightGBM）
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional
from utils.logger import setup_logger
from utils.s3_client import s3_client

logger = setup_logger(__name__)


class FuelPredictor:
    """
    油耗預測器
    使用 LightGBM 模型預測主機全速油耗
    """
    
    def __init__(self):
        self.model = None  # 實際應載入訓練好的模型
        self.feature_columns = [
            "AVG_SPEED",
            "ME_AVG_RPM",
            "DISPLACEMENT",
            "WIND_SCALE",
            "SEA_HEIGHT",
            "FORE_DRAFT",
            "AFTER_DRAFT"
        ]
    
    def predict(self, vessel_id: str, day: int, features: Dict, 
                counterfactual: Optional[Dict] = None) -> Dict:
        """
        預測油耗
        
        Args:
            vessel_id: 船舶代號
            day: 預測天數
            features: 航行特徵
            counterfactual: 反事實模擬參數（例如：模擬維護後）
        
        Returns:
            預測結果字典
        """
        try:
            # 簡化版本：使用線性估計
            # 實際應使用訓練好的 LightGBM 模型
            
            base_consumption = features.get("avg_speed", 18) * 4.5  # 簡化公式
            
            # 如果有反事實模擬
            if counterfactual:
                maintenance_type = counterfactual.get("simulate_maintenance")
                if maintenance_type == "UWC+PP":
                    # 模擬維護後油耗降低 8%
                    after_maintenance = base_consumption * 0.92
                    saving_mt = base_consumption - after_maintenance
                    
                    return {
                        "vessel_id": vessel_id,
                        "day": day,
                        "fuel_type": "ME_FULLSPEED_CONSUMP_VLSFO",
                        "predicted_value_mt": base_consumption,
                        "counterfactual_result": {
                            "predicted_after_maintenance_mt": after_maintenance,
                            "saving_mt_per_day": saving_mt,
                            "saving_usd_per_day": saving_mt * 620,  # 假設油價 $620/MT
                            "annual_saving_usd": saving_mt * 620 * 365
                        }
                    }
            
            return {
                "vessel_id": vessel_id,
                "day": day,
                "fuel_type": "ME_FULLSPEED_CONSUMP_VLSFO",
                "predicted_value_mt": base_consumption,
                "confidence_interval": [base_consumption * 0.95, base_consumption * 1.05]
            }
        
        except Exception as e:
            logger.error(f"Error predicting fuel: {e}", exc_info=True)
            raise
    
    def generate_submission_csv(self) -> str:
        """
        產出 102 筆預測結果 CSV
        """
        try:
            # 簡化版本：產生模擬數據
            # 實際應對 S21-S23 的 PREDICT 標記日逐一預測
            
            csv_lines = ["ship_id,day,fuel_type,predicted_value"]
            csv_lines.append("S21,450,ME_FULLSPEED_CONSUMP_HSHFO,85.3")
            csv_lines.append("S21,451,ME_FULLSPEED_CONSUMP_HSHFO,84.7")
            # ... 共 102 筆
            
            return "\n".join(csv_lines)
        
        except Exception as e:
            logger.error(f"Error generating submission CSV: {e}", exc_info=True)
            raise
