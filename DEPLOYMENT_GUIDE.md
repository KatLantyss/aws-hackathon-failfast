# AWS Lambda 後端部署指南

**目標**：將船舶效能分析系統後端部署到 AWS Lambda  
**技術棧**：AWS Lambda + DynamoDB + Serverless Framework

---

## 📋 前置條件

### 1. AWS 帳號和憑證配置
```bash
# 確保 AWS 憑證已配置
~/.aws/credentials
~/.aws/config

# 檢查憑證
aws sts get-caller-identity
```

### 2. 安裝工具
```bash
# 安裝 Serverless Framework
npm install -g serverless

# 安裝 AWS CLI
pip install awscli
```

### 3. 檢查依賴
```bash
cd /Users/rongrong77/aws-ai-hackathon/backend-api
pip install -r requirements.txt
```

---

## 🚀 部署步驟

### 第 1 步：準備代碼
```bash
cd /Users/rongrong77/aws-ai-hackathon/backend-api

# 確保所有必要文件存在
ls -la handler.py maintenance_advisor.py slope_based_analysis.py requirements.txt serverless.yml
```

### 第 2 步：配置 AWS 區域和帳戶（可選）

如需部署到其他區域或帳戶，編輯 `serverless.yml`：

```yaml
provider:
  name: aws
  runtime: python3.12
  region: us-east-1  # ← 修改區域
  # 或設置帳戶 ID：
  accountId: YOUR_AWS_ACCOUNT_ID
```

### 第 3 步：部署到 Lambda

```bash
# 完整部署
serverless deploy

# 或只部署特定函數
serverless deploy function -f api

# 監控日誌
serverless logs -f api -t
```

---

## 📊 部署配置詳情

### serverless.yml 概覽

**服務配置**：
```yaml
service: ship-analysis-api
```

**運行時環境**：
```yaml
provider:
  runtime: python3.12
  memorySize: 1024 MB       # 可根據需要調整
  timeout: 29 seconds       # Lambda 最大 15 分鐘，此處設 29 秒
  region: us-east-1
```

**DynamoDB 表訪問**：
```yaml
VESSEL_TABLE: ship-analysis-dev-vessel-data
MAINT_TABLE: ship-analysis-dev-maintenance-events
FLEET_SUMMARY_TABLE: ship-analysis-dev-fleet-summary
```

**IAM 權限**：
```yaml
iam:
  role:
    statements:
      - Effect: Allow
        Action:
          - dynamodb:Query
          - dynamodb:Scan
          - dynamodb:GetItem
        Resource:
          - arn:aws:dynamodb:us-east-1:151274905459:table/*
```

### API 端點映射

| 路徑 | 方法 | 功能 |
|------|------|------|
| `health` | GET | 健康檢查 |
| `api/v1/vessels` | GET | 所有船舶列表 |
| `api/v1/vessels/{vessel_id}` | GET | 單船詳情 |
| `api/v1/vessels/{vessel_id}/speed-loss` | GET | Speed Loss Dashboard |
| `api/v1/fleet/overview` | GET | **新增**：船隊概覽 |
| `api/v1/fleet/summary` | GET | 船隊摘要 |
| `api/v1/fleet/ranking` | GET | 優先級排序 |
| `api/v1/predict/fuel-consumption` | POST | 燃油預測 |

---

## 🔧 部署後驗證

### 1. 檢查部署狀態
```bash
# 查看已部署函數
serverless info

# 查看最近的日誌
serverless logs -f api -t

# 查看指標
aws lambda get-function-concurrency --function-name ship-analysis-api-dev-api
```

### 2. 測試 API
```bash
# 獲取部署後的 URL
ENDPOINT=$(serverless info | grep "POST\|GET" | head -1 | awk '{print $3}')

# 測試健康檢查
curl $ENDPOINT/health

# 測試船隊概覽
curl $ENDPOINT/api/v1/fleet/overview

# 測試燃油預測
curl -X POST $ENDPOINT/api/v1/predict/fuel-consumption \
  -H "Content-Type: application/json" \
  -d '{"vessel_id": "S1", "noon_day": 1000}'
```

### 3. 監控成本
```bash
# 查看 Lambda 調用次數
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=ship-analysis-api-dev-api \
  --start-time 2026-07-17T00:00:00Z \
  --end-time 2026-07-18T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

---

## 🐛 故障排查

### 問題 1：Python 版本不兼容
```
Error: Function layer error: Unable to import module 'handler'
```

**解決**：
```yaml
provider:
  runtime: python3.12  # 改為 python3.11 或 python3.10
```

### 問題 2：缺少依賴
```
Error: ModuleNotFoundError: No module named 'xgboost'
```

**解決**：
```bash
# 重新安裝依賴並部署
pip install -r requirements.txt --target ./vendor
serverless deploy
```

### 問題 3：DynamoDB 權限不足
```
Error: An error occurred (AccessDeniedException)
```

**解決**：檢查 IAM 角色是否有 DynamoDB 訪問權限：
```bash
aws iam list-attached-role-policies --role-name ship-analysis-api-dev-us-east-1-lambdaRole
```

### 問題 4：冷啟動超時
```
Error: Task timed out after 29.00 seconds
```

**解決**：增加超時時間和內存：
```yaml
provider:
  memorySize: 2048  # 增加至 2GB
  timeout: 60       # 增加至 60 秒
```

---

## 📈 性能優化

### 1. 減少冷啟動時間
```bash
# 使用 Lambda Layers 分離依賴
serverless plugin install -n serverless-python-requirements
```

### 2. 啟用 Lambda 預留併發
```bash
aws lambda put-function-concurrency \
  --function-name ship-analysis-api-dev-api \
  --reserved-concurrent-executions 100
```

### 3. 配置 CloudFront CDN
```yaml
# 在 serverless.yml 中添加
plugins:
  - serverless-plugin-cloudfront
```

---

## 🔐 安全最佳實踐

### 1. 環境變數加密
```yaml
provider:
  environment:
    # DynamoDB 表名保存在 Parameter Store
    VESSEL_TABLE: !Sub '{{resolve:ssm:/ship-analysis/vessel-table}}'
```

### 2. API 認證
```yaml
functions:
  api:
    events:
      - http:
          path: api/v1/vessels
          method: get
          # 添加 API Key 認證
          authorizer:
            type: aws_iam
```

### 3. 日誌加密
```bash
# 啟用 CloudWatch Logs 加密
aws logs put-resource-policy \
  --policy-name LambdaLogEncryption \
  --policy-text file://policy.json
```

---

## 📝 監控和告警

### 設置 CloudWatch 告警
```bash
# 告警：函數錯誤率 > 1%
aws cloudwatch put-metric-alarm \
  --alarm-name ship-analysis-api-errors \
  --alarm-description "Alert if error rate > 1%" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold

# 告警：持續時間 > 10 秒
aws cloudwatch put-metric-alarm \
  --alarm-name ship-analysis-api-duration \
  --alarm-description "Alert if duration > 10s" \
  --metric-name Duration \
  --namespace AWS/Lambda \
  --statistic Average \
  --period 300 \
  --threshold 10000 \
  --comparison-operator GreaterThanThreshold
```

---

## 🔄 更新和回滾

### 更新代碼
```bash
# 編輯代碼後
git add .
git commit -m "Update handler logic"

# 重新部署
serverless deploy
```

### 查看版本
```bash
# 列出所有版本
aws lambda list-versions-by-function --function-name ship-analysis-api-dev-api

# 查看特定版本的代碼
aws lambda get-function --function-name ship-analysis-api-dev-api:1
```

### 回滾到上一版本
```bash
# 更新別名指向之前的版本
aws lambda update-alias \
  --function-name ship-analysis-api-dev-api \
  --name live \
  --function-version 5  # 版本號
```

---

## 📊 成本估算

### 月度成本範例（假設條件）
- 請求數：10M/月
- 執行時間：平均 2 秒
- 內存：1024 MB

```
計算：
- 月度調用：10,000,000
- GB-秒：10,000,000 × 2 ÷ 128 × 1 = 156,250 GB-s
- Lambda 成本：156,250 × $0.0000166667 = $2.60
- 請求成本：10,000,000 × $0.0000002 = $2.00
- DynamoDB 讀取：50M 請求 × $0.00013 = $6.50
- 總計：約 $11/月

注：實際成本取決於實際使用情況
```

---

## ✅ 部署檢查清單

- [ ] AWS 憑證已配置
- [ ] 所有依賴已安裝
- [ ] serverless.yml 已更新（新端點）
- [ ] handler.py 包含所有新函數
- [ ] DynamoDB 表已存在且有數據
- [ ] IAM 角色有必要權限
- [ ] 環境變數已正確設置
- [ ] 部署前已測試本地運行

---

## 🚀 一鍵部署腳本

```bash
#!/bin/bash

set -e

echo "🚀 開始部署 Ship Analysis API..."

cd /Users/rongrong77/aws-ai-hackathon/backend-api

# 檢查依賴
echo "✓ 檢查依賴..."
pip install -r requirements.txt

# 驗證配置
echo "✓ 驗證 serverless.yml..."
serverless validate

# 部署
echo "✓ 部署到 AWS Lambda..."
serverless deploy

# 取得端點
echo "✓ 取得部署信息..."
serverless info

echo "✅ 部署完成！"
```

保存為 `deploy.sh` 並運行：
```bash
chmod +x deploy.sh
./deploy.sh
```

---

**部署完成！系統已上線。** 🎉

前端配置 `VITE_BACKEND_BASE_URL` 為 Lambda API Gateway 的端點 URL 即可。
