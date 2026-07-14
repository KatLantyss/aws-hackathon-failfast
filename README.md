# 🚢 陽明海運 AI 黑客松 — 船舶效能分析系統

AI 驅動的船舶速度損失分析與油耗預測平台，基於 ISO 19030 框架，支援水下清潔（UWC）、螺旋槳拋光（PP）反事實推論與商務決策建議。

---

## 架構

```
CloudFront (https://d1yvzz0da29zvi.cloudfront.net)
    └─ EC2 (ECS EC2 launch type, Elastic IP 52.45.130.183)
           └─ Docker container (FastAPI + XGBoost + boto3)
                  └─ DynamoDB (21,282 筆航行日報 + 77 筆養護事件)
```

前端靜態資源另行部署（或 `make dev-frontend` 本機開發）。

---

## 快速開始

### 前置需求

- Docker Desktop（已安裝並執行中）
- Node.js 18+（前端）
- AWS CLI 已設定 `hackathon` profile
- Python 3.11+（跑批次預測 script 用）

### 1. clone & 安裝

```bash
git clone <repo-url>
cd aws-ai-hackathon

# 安裝前端 npm 套件（只需一次）
cd frontend && npm install && cd ..
```

### 2. 設定環境變數

```bash
# 複製 env 範本
cp frontend/.env.example frontend/.env.local
```

`.env.local` 預設已設定 `VITE_BACKEND_BASE_URL=http://localhost:8000`，本機開發不需修改。

> **Voicebot / Chatbot 功能**需要額外填入 API keys：
> ```
> ANTHROPIC_API_KEY=sk-ant-...
> OPENAI_API_KEY=sk-...
> ```

### 3. 啟動開發環境

```bash
make dev
```

這個指令會：
1. 背景啟動 Docker container（backend API，port 8000）
2. 前景啟動 Vite dev server（frontend，port 5173）

瀏覽器開啟 **http://localhost:5173** 即可使用。

---

## Makefile 指令

| 指令 | 說明 |
|---|---|
| `make dev` | 同時啟動 backend（Docker）+ frontend（Vite）|
| `make dev-api` | 只啟動 backend Docker container |
| `make dev-frontend` | 只啟動 frontend Vite dev server |
| `make stop` | 停止 backend container |
| `make build` | 重新 build Docker image（arm64，本機測試用）|
| `make predict` | 跑批次預測，輸出 `backend-api/submission.csv` |
| `make predict URL=http://localhost:8000` | 批次預測打本機 |
| `make clean` | 清除 container 與 __pycache__ |

---

## 部署端點

| 環境 | URL |
|---|---|
| **CloudFront（生產）** | https://d1yvzz0da29zvi.cloudfront.net |
| **EC2 直連** | http://52.45.130.183:8000 |
| **本機開發** | http://localhost:8000 |

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
| POST | `/api/v1/predict/fuel-consumption` | XGBoost 油耗預測 + UWC/PP 反事實 |

---

## 油耗預測提交

對 S21~S23 的 102 個 PREDICT 標記日進行批次預測：

```bash
# 打 CloudFront（生產模型）
make predict

# 打本機（需先 make dev-api）
make predict URL=http://localhost:8000
```

輸出 `backend-api/submission.csv`，格式符合題目要求：

```
ship_id,day,fuel_type,predicted_value
S22,927,ME_FULLSPEED_CONSUMP_HSHFO,72.27
...
```

---

## 專案結構

```
aws-ai-hackathon/
├── Makefile                     # 開發指令入口
├── backend/
│   └── hackathon-data/          # 原始資料集
│       ├── vt_fd.csv            # 15 艘船 × 5 年航行日報（21,282 筆）
│       └── maintenance.csv      # 養護事件記錄（77 筆）
├── backend-api/                 # FastAPI + Docker 後端
│   ├── handler.py               # 所有 API 邏輯 + XGBoost 推論
│   ├── app.py                   # FastAPI routes
│   ├── Dockerfile               # Docker build
│   ├── requirements.txt
│   ├── predict_submit.py        # 批次預測 → submission.csv
│   ├── submission.csv           # 102 筆預測結果（已產出）
│   ├── API.md                   # API 詳細文件
│   └── model/
│       └── model_v3.pkl         # XGBoost 模型（29 features）
└── frontend/                    # Vue 3 前端
    ├── .env.example             # 環境變數範本
    └── src/
        ├── services/backend.ts  # API client
        └── ...
```

---

## 評分對應

| 評分項目 | 配分 | 對應功能 |
|---|---|---|
| Speed Loss Dashboard | 30% | `/speed-loss` + `/speed-loss-attribution` |
| 油耗預測正確性 | 25% | `submission.csv`（102 筆，已完成）|
| 商務決策價值 | 20% | `/maintenance-recommendation` + UWC/PP 反事實推論 |
| 技術可行性 | 15% | ECS EC2 + CloudFront + XGBoost model |
| AI 協作創意 | 10% | Voicebot / Chatbot（Anthropic Claude + OpenAI STT）|
