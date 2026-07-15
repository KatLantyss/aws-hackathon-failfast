# 🚀 AWS Lambda 部署 — 快速開始

## 部署前檢查清單

```bash
# 1. 檢查 AWS 憑證
aws sts get-caller-identity

# 2. 檢查 Serverless Framework
serverless --version

# 3. 進入後端目錄
cd backend-api

# 4. 檢查必要檔案
ls -la handler.py serverless.yml requirements.txt maintenance_advisor.py slope_based_analysis.py
```

## 一鍵部署

### 方式 1：使用部署腳本（推薦）
```bash
cd backend-api
chmod +x deploy.sh
./deploy.sh
```

### 方式 2：手動部署
```bash
cd backend-api

# 安裝依賴
pip install -r requirements.txt

# 驗證配置
serverless validate

# 部署
serverless deploy

# 查看結果
serverless info
```

## 部署後配置

### 前端環境變數
編輯 `.env.local` 或 `.env.development`：

```env
VITE_BACKEND_BASE_URL=https://your-api-id.execute-api.us-east-1.amazonaws.com/dev
```

### 測試部署
```bash
# 複製下方的 API URL
ENDPOINT="https://your-api-id.execute-api.us-east-1.amazonaws.com/dev"

# 健康檢查
curl $ENDPOINT/health

# 獲取船隊概覽
curl $ENDPOINT/api/v1/fleet/overview

# 預測燃油
curl -X POST $ENDPOINT/api/v1/predict/fuel-consumption \
  -H "Content-Type: application/json" \
  -d '{"vessel_id":"S1","noon_day":1000}'
```

## 查看日誌

```bash
cd backend-api

# 實時日誌
serverless logs -f api -t

# 過去 30 分鐘日誌
serverless logs -f api --startTime 30m

# 查看特定錯誤
serverless logs -f api | grep "ERROR"
```

## 故障排查

### 部署失敗
```bash
# 檢查 AWS 憑證
aws sts get-caller-identity

# 檢查 IAM 權限
aws iam get-user

# 驗證 DynamoDB 表存在
aws dynamodb list-tables
```

### 運行時錯誤
```bash
# 查看完整日誌
serverless logs -f api -t --verbose

# 查看函數詳情
aws lambda get-function-configuration --function-name ship-analysis-api-dev-api
```

### 冷啟動超時
如果看到 "Task timed out after 29 seconds"，編輯 `serverless.yml`：

```yaml
provider:
  memorySize: 2048  # 從 1024 增加至 2048
  timeout: 60       # 從 29 增加至 60
```

然後重新部署：
```bash
serverless deploy
```

## 成本監控

```bash
# 查看 Lambda 調用次數
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=ship-analysis-api-dev-api \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S)Z \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S)Z \
  --period 3600 \
  --statistics Sum

# 查看 Lambda 錯誤
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=ship-analysis-api-dev-api \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S)Z \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S)Z \
  --period 3600 \
  --statistics Sum
```

## 部署完成後

✅ **後端已在雲端運行！**

- 🔗 API 端點：查看 `serverless info` 的輸出
- 📊 監控：AWS CloudWatch 控制台
- 🔐 日誌：`serverless logs -f api -t`
- 📈 指標：AWS Lambda 控制台

---

**下一步**：配置前端的 `VITE_BACKEND_BASE_URL`，然後啟動前端 dev server。

