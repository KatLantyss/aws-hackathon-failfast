"""
配置管理 - 環境變數讀取
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """應用配置"""
    
    # 環境
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "dev")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # AWS 資源
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-northeast-1")
    S3_DATA_BUCKET: str = os.getenv("S3_DATA_BUCKET", "")
    S3_RAW_PREFIX: str = os.getenv("S3_RAW_PREFIX", "raw/")
    
    # DynamoDB 表名
    DYNAMODB_SPEED_LOSS: str = os.getenv("DYNAMODB_SPEED_LOSS", "")
    DYNAMODB_PREDICTIONS: str = os.getenv("DYNAMODB_PREDICTIONS", "")
    DYNAMODB_MAINTENANCE: str = os.getenv("DYNAMODB_MAINTENANCE", "")
    DYNAMODB_API_CACHE: str = os.getenv("DYNAMODB_API_CACHE", "")
    
    # 快取設定
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
    
    # 模型設定
    MODEL_VERSION: str = os.getenv("MODEL_VERSION", "v1.0.0")
    
    # X-Ray 追蹤
    ENABLE_XRAY: bool = os.getenv("ENABLE_XRAY", "false").lower() == "true"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
