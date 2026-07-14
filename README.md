# 🚢 陽明海運 AI 黑客松 — 船舶效能分析系統

AI 驅動的船舶速度損失分析與油耗預測平台，基於 ISO 19030 框架，支援水下清潔（UWC）、螺旋槳拋光（PP）反事實推論與商務決策建議。

---

## 架構

```
CloudFront (https://d1yvzz0da29zvi.cloudfront.net)
  ├─ /*       → S3 bucket (靜態前端 SPA)
  └─ /api/*   → EC2 52.45.130.183:8000
                  └─ ECS (EC2 launch type) Docker container
                         └─ FastAPI + XGBoost + boto3
                                └─ DynamoDB
                                     ├─ ship-analysis-dev-vessel-data       (21,282 筆航行日報)
                                     ├─ ship-analysis-dev-maintenance-events (77 筆養護事件)
                                     └─ ship-analysis-dev-fleet-summary      (15 艘船預計算摘要)
```

---

## 前置需求

| 工具 | 說明 |
|---|---|
| Docker Desktop | 後端 image build 用 |
| Node.js 18+ | 前端 npm build |
| Python 3.11+ | scripts/ 輔助工具 |
| AWS CLI v2 | 設定 `hackathon` profile（見下方）|
| boto3 | `pip install boto3`（scripts/ 需要）|

---

## 本機開發（make dev）

### 1. Clone & 安裝

```bash
git clone <repo-url>
cd aws-ai-hackathon
cd frontend && npm install && cd ..
```

### 2. 設定 AWS Credentials

每次 credentials 過期時更新 `~/.aws/credentials` 的 `[hackathon]` section：

```ini
[hackathon]
aws_access_key_id     = ASIA...
aws_secret_access_key = ...
aws_session_token     = ...
```

或用 AWS CLI 設定：

```bash
aws configure set aws_access_key_id     ASIA...  --profile hackathon
aws configure set aws_secret_access_key ...       --profile hackathon
aws configure set aws_session_token     ...       --profile hackathon
aws configure set region                us-east-1 --profile hackathon
```

驗證：
```bash
aws sts get-caller-identity --profile hackathon
```

### 3. 設定前端環境變數（只需一次）

```bash
cp frontend/.env.example frontend/.env.local
# .env.local 預設已包含：
# VITE_BACKEND_BASE_URL=http://localhost:8000
```

> **Voicebot / Chatbot 功能**需額外填入：
> ```
> ANTHROPIC_API_KEY=sk-ant-...
> OPENAI_API_KEY=sk-...
> ```

### 4. 啟動

```bash
make dev
```

| 服務 | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |

`make dev` 會：
1. 停止舊的 uvicorn/Docker container（避免 port 衝突）
2. 直接啟動 uvicorn（不用 Docker），使用 hackathon profile 的 credentials
3. 背景啟動 Vite dev server

---

## 生產部署（make prod）

> ⚠️ **需要 Docker 執行中、AWS credentials 有效（hackathon profile）**

### 一鍵全部部署

```bash
make prod
```

包含：
1. **後端**：build linux/amd64 Docker image → push ECR → 新 ECS task definition（含 FLEET_SUMMARY_TABLE）→ force-new-deployment → 自動停舊 task → 等待健康檢查
2. **前端**：`npm run build`（注入 CloudFront URL）→ S3 sync → CloudFront invalidation

完成後，`https://d1yvzz0da29zvi.cloudfront.net` 即為最新版。

### 只部署後端

```bash
make prod-backend
```

### 只部署前端

```bash
make prod-frontend
```

### 更新 fleet-summary DynamoDB table

原始資料（vt_fd.csv + maintenance.csv）有變動時，重新計算並寫入：

```bash
cd backend-api
AWS_PROFILE=hackathon python3 build_fleet_summary.py
```

---

## 所有 Makefile 指令

| 指令 | 說明 |
|---|---|
| `make dev` | 本機開發：uvicorn backend + Vite frontend |
| `make dev-api` | 只啟動 backend（uvicorn） |
| `make dev-frontend` | 只啟動 frontend（Vite） |
| `make stop` | 停止 uvicorn backend |
| `make stop-all` | 停止 backend + frontend |
| `make prod` | 生產部署：後端 ECS + 前端 S3/CloudFront |
| `make prod-backend` | 只部署後端到 ECS |
| `make prod-frontend` | 只部署前端到 S3 + CloudFront |
| `make prod-login` | ECR docker login |
| `make build` | build Docker image（本機 arm64 測試用）|
| `make predict` | 批次預測 → `backend-api/submission.csv`（打 CloudFront）|
| `make predict URL=http://localhost:8000` | 批次預測打本機 |
| `make clean` | 清除 container 與 `__pycache__` |

---

## 生產端點

| 環境 | URL |
|---|---|
| **生產（CloudFront）** | https://d1yvzz0da29zvi.cloudfront.net |
| **EC2 直連（backend only）** | http://52.45.130.183:8000 |
| **本機 frontend** | http://localhost:5173 |
| **本機 backend** | http://localhost:8000 |

---

## API 一覽

完整說明見 [`backend-api/API.md`](backend-api/API.md)。

| Method | Path | 說明 |
|---|---|---|
| GET | `/health` | 健康檢查 |
| GET | `/api/v1/vessels` | 船艦列表（15 艘）|
| GET | `/api/v1/vessels/{id}` | 單船統計摘要 |
| GET | `/api/v1/vessels/{id}/noon-reports` | 航行日報 |
| GET | `/api/v1/vessels/{id}/speed-loss` | Speed Loss 趨勢（ISO 19030）|
| GET | `/api/v1/vessels/{id}/speed-loss-attribution` | 船殼/螺旋槳歸因分析 |
| GET | `/api/v1/vessels/{id}/maintenance-events` | 養護事件列表 |
| GET | `/api/v1/vessels/{id}/maintenance-recommendation` | 維護建議 |
| GET | `/api/v1/fleet/ranking` | 船隊效能排名 |
| GET | `/api/v1/fleet/summary` | 船隊綜合摘要（KPI 儀表板用）|
| POST | `/api/v1/predict/fuel-consumption` | XGBoost 油耗預測 + UWC/PP 反事實 |

---

## 油耗預測提交

對 S21~S23 的 102 個 PREDICT 標記日進行批次預測：

```bash
make predict           # 打 CloudFront（生產）
make predict URL=http://localhost:8000  # 打本機
```

輸出 `backend-api/submission.csv`：

```
ship_id,day,fuel_type,predicted_value
S22,927,ME_FULLSPEED_CONSUMP_HSHFO,72.27
...
```

---

## 專案結構

```
aws-ai-hackathon/
├── Makefile                        # 所有指令入口
├── scripts/
│   ├── gen_taskdef.py              # 產生 ECS backend task definition JSON
│   ├── setup_s3_frontend.py        # 建立 S3 bucket + 設定 CloudFront routing
│   └── patch_cloudfront.py         # CloudFront config patch helper
├── backend/
│   └── hackathon-data/             # 原始資料集
│       ├── vt_fd.csv               # 15 艘船 × 5 年航行日報（21,282 筆）
│       └── maintenance.csv         # 養護事件記錄（77 筆）
├── backend-api/                    # FastAPI 後端
│   ├── handler.py                  # 所有 API 邏輯 + XGBoost 推論
│   ├── app.py                      # FastAPI routes + startup warmup
│   ├── build_fleet_summary.py      # 從 CSV 計算並寫入 fleet-summary DynamoDB
│   ├── Dockerfile                  # linux/amd64 production image
│   ├── requirements.txt
│   ├── predict_submit.py           # 批次預測 → submission.csv
│   ├── submission.csv              # 102 筆預測結果
│   ├── API.md                      # API 詳細文件
│   └── model/
│       └── model_v3.pkl            # XGBoost 模型（29 features）
└── frontend/                       # Vue 3 前端
    ├── .env.example                # 環境變數範本
    ├── .env.local                  # 本機設定（不進 git）
    └── src/
        ├── api/
        │   ├── client.ts           # REST API 型別 + fetch functions
        │   └── adapter.ts          # API response → VesselSummary 轉換
        ├── views/                  # 頁面元件
        └── services/backend.ts     # 後端 API client（typed）
```

---

## 常見問題

**Q: `make dev` 後 API 一直回 403**
→ AWS credentials 過期，重新設定 `hackathon` profile。

**Q: `make prod-backend` 後後端沒更新**
→ ECS host-network mode 導致 port 衝突，Makefile 已自動處理（停舊 task、等待健康檢查）。若仍有問題，手動停 task：
```bash
AWS_PROFILE=hackathon AWS_DEFAULT_REGION=us-east-1 \
  aws ecs list-tasks --cluster ship-analysis
# 複製 task ARN，然後：
AWS_PROFILE=hackathon AWS_DEFAULT_REGION=us-east-1 \
  aws ecs stop-task --cluster ship-analysis --task <task-arn>
```

**Q: 前端顯示舊資料**
→ CloudFront 有 cache，手動 invalidate：
```bash
AWS_PROFILE=hackathon AWS_DEFAULT_REGION=us-east-1 \
  aws cloudfront create-invalidation --distribution-id EYQC35Y9OSEQD --paths "/*"
```
