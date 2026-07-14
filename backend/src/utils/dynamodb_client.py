"""
DynamoDB 客戶端 - 快取管理
"""
import boto3
import json
import time
from typing import Optional, Dict, Any, List
from decimal import Decimal
from .config import settings
from .logger import setup_logger

logger = setup_logger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """DynamoDB Decimal 編碼器"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


class DynamoDBClient:
    """DynamoDB 快取客戶端"""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb', region_name=settings.AWS_REGION)
        self.speed_loss_table = self.dynamodb.Table(settings.DYNAMODB_SPEED_LOSS)
        self.predictions_table = self.dynamodb.Table(settings.DYNAMODB_PREDICTIONS)
        self.maintenance_table = self.dynamodb.Table(settings.DYNAMODB_MAINTENANCE)
        self.api_cache_table = self.dynamodb.Table(settings.DYNAMODB_API_CACHE)
    
    def _convert_floats_to_decimal(self, data: Any) -> Any:
        """轉換 float 為 Decimal（DynamoDB 要求）"""
        if isinstance(data, dict):
            return {k: self._convert_floats_to_decimal(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._convert_floats_to_decimal(item) for item in data]
        elif isinstance(data, float):
            return Decimal(str(data))
        return data
    
    def _add_ttl(self, item: Dict[str, Any], ttl_seconds: Optional[int] = None) -> Dict[str, Any]:
        """添加 TTL 時間戳"""
        if ttl_seconds is None:
            ttl_seconds = settings.CACHE_TTL_SECONDS
        item['ttl'] = int(time.time()) + ttl_seconds
        return item
    
    # Speed Loss 快取
    def get_speed_loss(self, vessel_id: str, day: int) -> Optional[Dict]:
        """取得 Speed Loss 快取"""
        try:
            response = self.speed_loss_table.get_item(
                Key={'vessel_id': vessel_id, 'day': day}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error getting speed loss cache: {e}")
            return None
    
    def put_speed_loss(self, vessel_id: str, day: int, data: Dict, version: str = "v1"):
        """儲存 Speed Loss 快取"""
        try:
            item = {
                'vessel_id': vessel_id,
                'day': day,
                'calculation_version': version,
                'data': self._convert_floats_to_decimal(data)
            }
            item = self._add_ttl(item)
            self.speed_loss_table.put_item(Item=item)
        except Exception as e:
            logger.error(f"Error putting speed loss cache: {e}")
    
    def batch_put_speed_loss(self, items: List[Dict]):
        """批量儲存 Speed Loss"""
        try:
            with self.speed_loss_table.batch_writer() as batch:
                for item in items:
                    item = self._add_ttl(item)
                    batch.put_item(Item=self._convert_floats_to_decimal(item))
        except Exception as e:
            logger.error(f"Error batch putting speed loss: {e}")
    
    # 預測快取
    def get_prediction(self, vessel_id: str, day: int, fuel_type: str) -> Optional[Dict]:
        """取得預測快取"""
        try:
            prediction_key = f"day#{day}#fuel#{fuel_type}"
            response = self.predictions_table.get_item(
                Key={'vessel_id': vessel_id, 'prediction_key': prediction_key}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error getting prediction cache: {e}")
            return None
    
    def put_prediction(self, vessel_id: str, day: int, fuel_type: str, 
                      predicted_value: float, model_version: str):
        """儲存預測快取"""
        try:
            prediction_key = f"day#{day}#fuel#{fuel_type}"
            item = {
                'vessel_id': vessel_id,
                'prediction_key': prediction_key,
                'model_version': model_version,
                'day': day,
                'fuel_type': fuel_type,
                'predicted_value': Decimal(str(predicted_value))
            }
            item = self._add_ttl(item)
            self.predictions_table.put_item(Item=item)
        except Exception as e:
            logger.error(f"Error putting prediction cache: {e}")
    
    # API 快取
    def get_api_cache(self, cache_key: str) -> Optional[Dict]:
        """取得 API 快取"""
        try:
            response = self.api_cache_table.get_item(Key={'cache_key': cache_key})
            item = response.get('Item')
            if item and item.get('ttl', 0) > time.time():
                return json.loads(item.get('data', '{}'))
            return None
        except Exception as e:
            logger.error(f"Error getting API cache: {e}")
            return None
    
    def put_api_cache(self, cache_key: str, data: Dict, ttl_seconds: Optional[int] = None):
        """儲存 API 快取"""
        try:
            item = {
                'cache_key': cache_key,
                'data': json.dumps(data, cls=DecimalEncoder)
            }
            item = self._add_ttl(item, ttl_seconds)
            self.api_cache_table.put_item(Item=item)
        except Exception as e:
            logger.error(f"Error putting API cache: {e}")


# 全域單例
dynamodb_client = DynamoDBClient()
