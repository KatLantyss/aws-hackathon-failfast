# Backend - Ship Performance Analysis API

FastAPI 服務，提供船舶效能分析、Speed Loss 計算與油耗預測 API。可獨立本地執行（讀取本地/S3 資料），亦可透過 Mangum 部署到 AWS Lambda。

## 環境需求

- Python >= 3.11
- AWS 憑證（用於存取 S3 / DynamoDB，本地開發若無真實資源可用假憑證，但呼叫到 S3/DynamoDB 的端點會失敗）

## 本地運行

### 1. 建立虛擬環境並安裝依賴

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 設定環境變數

複製根目錄的 `.env.example` 為 `backend/.env`（或直接 export），至少需要：

```bash
export ENVIRONMENT=dev
export LOG_LEVEL=DEBUG
export AWS_REGION=us-east-1
export S3_DATA_BUCKET=<your-s3-bucket>       # 需能連到此 bucket 才能讀取 vt_fd.csv / maintenance.csv
export S3_RAW_PREFIX=raw/
export DYNAMODB_SPEED_LOSS=<table-name>
export DYNAMODB_PREDICTIONS=<table-name>
export DYNAMODB_MAINTENANCE=<table-name>
export DYNAMODB_API_CACHE=<table-name>
```

> 沒有 AWS 憑證時，服務仍能啟動並回應 `/health`、`/api/docs` 等端點，但任何呼叫 S3 / DynamoDB 的路由（`/api/v1/vessels`、`/api/v1/predict/*` 等）會因無法連線而報錯。設定 `aws configure` 或 export `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` 以取得完整功能。

### 3. 啟動開發伺服器

```bash
cd src
python main.py
# 或使用 uvicorn 並開啟 auto-reload：
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

啟動後可存取：

- API 根路徑：http://localhost:8000/
- 健康檢查：http://localhost:8000/health
- **Swagger UI**：http://localhost:8000/api/docs
- ReDoc：http://localhost:8000/api/redoc
- OpenAPI JSON：http://localhost:8000/openapi.json

> 注意：`main.py` 會依 `ENVIRONMENT` 決定是否開放 `/api/docs`。當 `ENVIRONMENT=prod` 時 Swagger UI 與 ReDoc 會被關閉，僅在 `dev` 等非 prod 環境下可用。

## 靜態 Swagger 文件頁面（/docs）

除了伺服器內建的 `/api/docs`，本專案也提供了離線可看的 Swagger UI 頁面於 [`backend/docs/`](./docs)：

- `docs/index.html`：透過 CDN 載入的 Swagger UI，讀取同目錄下的 `openapi.json`
- `docs/openapi.json`：目前 API 的 OpenAPI schema 快照

### 開啟方式

```bash
cd backend/docs
python3 -m http.server 8080
# 開啟瀏覽器： http://localhost:8080/
```

（直接用瀏覽器打開 `index.html` 檔案也可以，但部分瀏覽器會擋 `fetch` 本地檔案，建議用簡易 HTTP server。）

### 更新 openapi.json 快照

當 API 路由或 schema 有變動時，重新產生快照：

```bash
cd backend/src
python3 -c "
import json
import main
with open('../docs/openapi.json', 'w', encoding='utf-8') as f:
    json.dump(main.app.openapi(), f, ensure_ascii=False, indent=2)
"
```

## 執行測試

目前專案尚未提供自動化測試套件。

## 專案結構

```
backend/
├── docs/                     # 靜態 Swagger UI 頁面
│   ├── index.html
│   └── openapi.json
├── hackathon-data/           # 原始資料（CSV）
├── requirements.txt
└── src/
    ├── main.py               # FastAPI 進入點
    ├── api/                  # 路由（vessels, speed_loss, predictions, maintenance, fleet）
    ├── ml/                   # 模型（fuel_predictor, speed_loss_calculator, train_fuel_model）
    └── utils/                 # config, logger, s3_client, dynamodb_client
```

## 部署

本服務透過 `Mangum` 包裝，可直接作為 AWS Lambda handler（`src/main.py` 中的 `handler`）。詳細部署結果與 API 清單見 [`DEPLOY_RESULT.md`](./DEPLOY_RESULT.md)。
