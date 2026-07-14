# 🚢 陽明海運 AI 黑客松 - 船舶效能分析系統

> 基於 AWS 的船舶速度損失分析與油耗預測平台

## 📋 專案概述

本系統針對陽明海運黑客松挑戰，提供：
1. **油耗預測模型** - 預測船舶主機全速油耗（102 個預測點）
2. **Speed Loss Dashboard** - ISO 19030 框架下的速度損失分析
3. **商務決策支援** - 維護建議、成本效益分析、反事實推論

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Vue 3)                          │
│              hosted on S3 + CloudFront                       │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼────────────────────────────────────┐
│                CloudFront Distribution                        │
│                   (CDN + Caching)                            │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  API Gateway (HTTP API)                      │
│            /api/v1/vessels, /predict, etc.                   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│              Lambda Function (FastAPI)                       │
│   - 5 API Routers (vessels, speed_loss, predictions...)     │
│   - ML Models (LightGBM fuel prediction)                    │
│   - Speed Loss Calculator (ISO 19030)                       │
└──────────┬────────────────────────┬─────────────────────────┘
           │                        │
     ┌─────▼─────┐           ┌─────▼─────┐
     │    S3     │           │ DynamoDB  │
     │  (Data)   │           │  (Cache)  │
     └───────────┘           └───────────┘
     raw/                    4 tables:
     - vt_fd.csv            - speed_loss
     - maintenance.csv      - predictions
                            - maintenance
                            - api_cache
```

## 🚀 快速開始

### 前置需求

- AWS CLI 已配置
- Terraform >= 1.5.0
- Python >= 3.11
- Node.js >= 18 (前端開發)

### 一鍵部署

```bash
# 1. 克隆專案
git clone <repo-url>
cd aws-ai-hackathon

# 2. 執行部署腳本
./deploy.sh
```

部署腳本會自動完成：
- ✅ 建立 Lambda 部署套件
- ✅ 使用 Terraform 部署 AWS 資源
- ✅ 上傳數據到 S3
- ✅ 顯示 API 端點

### 手動部署（進階）

#### Step 1: 建立 Lambda 套件

```bash
cd backend
./build_lambda.sh
```

產出：
- `lambda_layer.zip` - Python 依賴套件（FastAPI, pandas, LightGBM...）
- `lambda_function.zip` - 應用程式碼

#### Step 2: Terraform 部署

```bash
cd terraform

# 初始化
terraform init

# 檢查計劃
terraform plan

# 部署
terraform apply
```

#### Step 3: 上傳數據

```bash
# 取得 S3 bucket 名稱
BUCKET_NAME=$(cd terraform && terraform output -raw s3_data_bucket_name)

# 上傳 CSV
aws s3 cp backend/hackathon-data/vt_fd.csv "s3://${BUCKET_NAME}/raw/"
aws s3 cp backend/hackathon-data/maintenance.csv "s3://${BUCKET_NAME}/raw/"
```

## 📊 API 端點

### 核心 API

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/v1/vessels` | GET | 船舶列表 |
| `/api/v1/vessels/{id}` | GET | 船舶詳細資訊 |
| `/api/v1/vessels/{id}/noon-reports` | GET | 航行日報 |
| `/api/v1/vessels/{id}/speed-loss` | GET | Speed Loss 計算 |
| `/api/v1/vessels/{id}/speed-loss-attribution` | GET | 歸因分析 |
| `/api/v1/vessels/{id}/maintenance-events` | GET | 維護事件 |
| `/api/v1/vessels/{id}/maintenance-recommendation` | GET | 維護建議 |
| `/api/v1/predict/fuel-consumption` | POST | 油耗預測 |
| `/api/v1/predict/submit` | POST | 產出提交 CSV |
| `/api/v1/fleet/ranking` | GET | 船隊排名 |

### 健康檢查

```bash
curl https://<cloudfront-domain>/health
```

### API 文檔

訪問 `https://<cloudfront-domain>/api/docs` 查看完整的 Swagger UI。

## 🤖 ML 模型訓練

### 訓練油耗預測模型

```bash
cd backend/src/ml
python train_fuel_model.py
```

訓練流程：
1. 載入 vt_fd.csv 和 maintenance.csv
2. 特徵工程（13 個特徵）
3. 訓練 LightGBM 模型
4. 評估（RMSE, MAE, R², MAPE）
5. 儲存模型至 `models/fuel_model.pkl`

### 特徵列表

- 航行特徵：`AVG_SPEED`, `ME_AVG_RPM`, `DISPLACEMENT`
- 環境特徵：`WIND_SCALE`, `SEA_HEIGHT`, `SEA_WATER_TEMP`
- 船體特徵：`FORE_DRAFT`, `AFTER_DRAFT`, `MID_DRAFT`, `CARGO_ON_BOARD`
- 時間退化特徵：`days_since_dd`, `days_since_uwc`, `days_since_pp`
- 船型：`vessel_type` (W1/W2)

## 🗂️ 專案結構

```
aws-ai-hackathon/
├── backend/
│   ├── hackathon-data/          # 原始數據
│   │   ├── vt_fd.csv
│   │   └── maintenance.csv
│   ├── src/
│   │   ├── main.py              # FastAPI 主程式
│   │   ├── api/                 # API 路由
│   │   │   ├── vessels.py
│   │   │   ├── speed_loss.py
│   │   │   ├── predictions.py
│   │   │   ├── maintenance.py
│   │   │   └── fleet.py
│   │   ├── ml/                  # ML 模型
│   │   │   ├── fuel_predictor.py
│   │   │   ├── speed_loss_calculator.py
│   │   │   └── train_fuel_model.py
│   │   └── utils/               # 工具模組
│   │       ├── s3_client.py
│   │       ├── dynamodb_client.py
│   │       ├── config.py
│   │       └── logger.py
│   ├── requirements.txt
│   └── build_lambda.sh
├── terraform/
│   ├── provider.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── s3.tf
│   ├── dynamodb.tf
│   ├── lambda.tf
│   ├── api_gateway.tf
│   └── cloudfront.tf
├── frontend/                    # Vue 3 前端（已有）
├── deploy.sh                    # 一鍵部署腳本
└── README.md
```

## 🔧 Terraform 變數配置

建立 `terraform/terraform.tfvars`：

```hcl
aws_region    = "ap-northeast-1"
environment   = "dev"
project_name  = "ship-analysis"

# Lambda 配置
lambda_memory_size = 3008
lambda_timeout     = 900

# CloudFront
enable_cloudfront = true

# CORS（開發環境開放，生產環境限制）
cors_allowed_origins = ["*"]
```

## 💰 成本估算

### 開發/黑客松環境（48小時）

| 服務 | 用量 | 成本 |
|------|------|------|
| Lambda | 1M requests, 3GB memory | $0 (免費層) |
| API Gateway | 1M calls | $0 (免費層) |
| S3 | 5GB 儲存 | $0.12 |
| DynamoDB | 按需計費 | ~$5 |
| CloudFront | 50GB 流量 | ~$4 |
| CloudWatch Logs | 7 天保留 | ~$1 |
| **總計** | | **~$10-15** |

### 生產環境（每月）

估計 10K requests/day：
- Lambda: $30
- API Gateway: $3.5
- S3: $1
- DynamoDB: $15
- CloudFront: $20
- **總計: ~$70/month**

## 🧪 本地開發

### 後端開發

```bash
cd backend/src

# 安裝依賴
pip install -r ../requirements.txt

# 設定環境變數
export ENVIRONMENT=dev
export S3_DATA_BUCKET=local-test
export LOG_LEVEL=DEBUG

# 啟動開發伺服器
python main.py

# API 可在 http://localhost:8000 訪問
```

### 前端開發

```bash
cd frontend

# 安裝依賴
npm install

# 設定 API 端點（.env.local）
VITE_API_BASE_URL=http://localhost:8000

# 啟動開發伺服器
npm run dev
```

## 📈 監控與日誌

### CloudWatch Logs

```bash
# Lambda 日誌
aws logs tail /aws/lambda/ship-analysis-dev-api --follow

# API Gateway 日誌
aws logs tail /aws/apigateway/ship-analysis-dev --follow
```

### CloudWatch Alarms

已配置告警：
- Lambda 錯誤率過高
- Lambda 執行時間過長
- API Gateway 4XX/5XX 錯誤
- DynamoDB 讀取限流

## 🧹 清理資源

```bash
cd terraform
terraform destroy
```

⚠️ 注意：這會刪除所有資源，包括 S3 數據和 DynamoDB 表。

## 🔐 安全最佳實踐

1. **S3 Bucket**
   - ✅ 已啟用版本控制
   - ✅ 已加密（AES256）
   - ✅ 已封鎖公開存取

2. **Lambda**
   - ✅ 最小權限 IAM role
   - ✅ 環境變數加密
   - ✅ VPC 隔離（可選）

3. **API Gateway**
   - ✅ HTTPS only
   - ✅ CORS 配置
   - ✅ 速率限制（2000 req/s）

4. **CloudFront**
   - ✅ TLS 1.2+
   - ✅ 壓縮啟用
   - ✅ 快取策略優化

## 📝 評分對應

| 評分項目 | 配分 | 對應功能 |
|---------|------|---------|
| Speed Loss Dashboard | 30% | `/vessels/{id}/speed-loss`, `/speed-loss-attribution` |
| 油耗預測正確性 | 25% | `/predict/fuel-consumption`, ML 模型訓練 |
| 商務決策價值 | 20% | `/maintenance-recommendation`, 反事實推論 |
| 技術可行性 | 15% | 完整的 Terraform + Lambda 部署 |
| AI 協作創意 | 10% | (前端已有 Chatbot 整合) |

## 🆘 故障排除

### Lambda 冷啟動慢

```hcl
# terraform/lambda.tf
# 啟用 Provisioned Concurrency
resource "aws_lambda_provisioned_concurrency_config" "ship_api" {
  function_name                     = aws_lambda_function.ship_api.function_name
  provisioned_concurrent_executions = 2
  qualifier                         = aws_lambda_function.ship_api.version
}
```

### DynamoDB 限流

改用 PROVISIONED 模式：

```hcl
# terraform/variables.tf
dynamodb_billing_mode = "PROVISIONED"
```

### S3 數據讀取失敗

檢查 IAM 權限和 bucket 名稱：

```bash
aws s3 ls s3://<bucket-name>/raw/
```

## 📚 參考資料

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [AWS Lambda Python](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [ISO 19030 Standard](https://www.iso.org/standard/63774.html)
- [LightGBM Documentation](https://lightgbm.readthedocs.io/)

## 👥 團隊

陽明海運 AI 黑客松團隊 - 2026

## 📄 授權

MIT License
