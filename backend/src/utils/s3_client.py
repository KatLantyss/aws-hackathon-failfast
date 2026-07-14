"""
S3 客戶端 - 數據讀取
"""
import boto3
import pandas as pd
from io import StringIO
from typing import Optional
from .config import settings
from .logger import setup_logger

logger = setup_logger(__name__)


class S3Client:
    """S3 數據存取客戶端"""
    
    def __init__(self):
        self.s3 = boto3.client('s3', region_name=settings.AWS_REGION)
        self.bucket = settings.S3_DATA_BUCKET
        self.prefix = settings.S3_RAW_PREFIX
    
    def read_csv(self, filename: str) -> pd.DataFrame:
        """讀取 CSV 檔案"""
        try:
            key = f"{self.prefix}{filename}"
            logger.info(f"Reading CSV from s3://{self.bucket}/{key}")
            
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            df = pd.read_csv(StringIO(content))
            
            logger.info(f"Successfully loaded {len(df)} rows from {filename}")
            return df
        except Exception as e:
            logger.error(f"Error reading CSV {filename}: {e}")
            raise
    
    def load_voyage_data(self) -> pd.DataFrame:
        """載入航行日報數據"""
        return self.read_csv("vt_fd.csv")
    
    def load_maintenance_data(self) -> pd.DataFrame:
        """載入維護事件數據"""
        return self.read_csv("maintenance.csv")
    
    def file_exists(self, filename: str) -> bool:
        """檢查檔案是否存在"""
        try:
            key = f"{self.prefix}{filename}"
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except:
            return False


# 全域單例
s3_client = S3Client()
