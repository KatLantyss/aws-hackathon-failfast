#!/bin/bash

# 船舶效能分析系統 AWS Lambda 部署腳本
# 用途：一鍵部署後端到 AWS Lambda

set -e

echo "🚀 開始部署 Ship Analysis API..."
echo "==============================================="

# 檢查必要工具
echo "✓ 檢查工具..."
command -v serverless >/dev/null 2>&1 || { echo "❌ 需要安裝 Serverless Framework: npm install -g serverless"; exit 1; }
command -v aws >/dev/null 2>&1 || { echo "❌ 需要安裝 AWS CLI"; exit 1; }

# 進入後端目錄
cd "$(dirname "$0")"
echo "✓ 進入目錄: $(pwd)"

# 檢查必要檔案
echo "✓ 檢查必要檔案..."
for file in handler.py maintenance_advisor.py slope_based_analysis.py requirements.txt serverless.yml; do
  if [ ! -f "$file" ]; then
    echo "❌ 缺少檔案: $file"
    exit 1
  fi
done

# 安裝依賴
echo "✓ 安裝 Python 依賴..."
pip install -q -r requirements.txt

# 驗證 serverless.yml
echo "✓ 驗證 serverless.yml..."
serverless validate

# 部署到 AWS Lambda
echo "✓ 部署到 AWS Lambda..."
serverless deploy --verbose

# 取得部署信息
echo ""
echo "==============================================="
echo "✅ 部署成功！"
echo "==============================================="
echo ""

# 顯示 API 端點
echo "📋 API 端點信息："
serverless info

echo ""
echo "🔗 API Gateway URL (複製到前端配置)："
serverless info --verbose | grep "endpoint:" || echo "請從上方 API endpoint 欄位複製"

echo ""
echo "📝 後續步驟："
echo "1. 複製 API Gateway URL"
echo "2. 更新前端的 VITE_BACKEND_BASE_URL 環境變數"
echo "3. npm run dev 啟動前端"
echo ""

echo "📊 查看日誌："
echo "  serverless logs -f api -t"
echo ""

echo "🧪 測試 API："
echo "  curl -X GET {API_URL}/health"
echo "  curl -X GET {API_URL}/api/v1/fleet/overview"
echo ""
