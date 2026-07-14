# Ship Performance Analysis API

**Base URL:** `https://4rh4qj5e3i.execute-api.us-east-1.amazonaws.com/dev`

**架構：** API Gateway → Lambda (Python 3.12) → DynamoDB

---

## 資料說明

| 資料 | DynamoDB Table | 筆數 |
|------|---------------|------|
| 船舶航行日報 | `ship-analysis-dev-vessel-data` | 21,282 筆 |
| 維護事件記錄 | `ship-analysis-dev-maintenance-events` | 77 筆 |

**船舶分類：**
- 訓練集：S1–S12（12 艘，5 年歷史數據）
- 預測集：S21–S23（3 艘，需要預測燃油消耗）

**時間軸：** `NOON_UTC` 為相對天數（0 = 第一天，1825 = 第 5 年末）

---

## Endpoints

### Health Check

```
GET /health
```

**Response:**
```json
{
  "status": "ok",
  "vessel_table": "ship-analysis-dev-vessel-data",
  "maint_table": "ship-analysis-dev-maintenance-events"
}
```

---

### 船舶列表

```
GET /api/v1/vessels
```

回傳所有 15 艘船（含分類）。

**Response:**
```json
{
  "vessels": [
    { "vessel_id": "S1", "type": "training" },
    { "vessel_id": "S21", "type": "prediction" }
  ],
  "total": 15
}
```

---

### 船舶概況

```
GET /api/v1/vessels/{vessel_id}
```

回傳單艘船的統計摘要（平均速度、燃耗、航次範圍）。

**Path params:** `vessel_id` — S1~S12, S21~S23

**Response:**
```json
{
  "vessel_id": "S1",
  "total_records": 1482,
  "avg_speed_kn": 14.23,
  "avg_consumption": 58.4,
  "avg_stw_kn": 14.51,
  "voyage_range": { "min": 28, "max": 49 }
}
```

---

### 航行日報（Noon Reports）

```
GET /api/v1/vessels/{vessel_id}/noon-reports
```

逐筆回傳每日正午報告，可依航次篩選。

**Query params:**

| 參數 | 說明 | 預設 |
|------|------|------|
| `limit` | 最大筆數 | 100 |
| `voyage` | 航次號碼 | （全部） |

**Response:**
```json
{
  "vessel_id": "S1",
  "count": 100,
  "records": [
    {
      "vessel_id": "S1",
      "noon_day": 0.0,
      "voyage": 28.0,
      "avg_speed_kn": 14.4,
      "speed_through_water": 14.68,
      "me_rpm": 51.8,
      "fore_draft": 14.9,
      "aft_draft": 15.0,
      "cargo_on_board": 91791.0,
      "wind_scale": 3.0,
      "sea_height": null,
      "horse_power": 13295.0,
      "me_consumption": null,
      "total_consump": 66.05,
      "sfoc": null,
      "me_slip": 13.23
    }
  ]
}
```

---

### Speed Loss 分析

```
GET /api/v1/vessels/{vessel_id}/speed-loss
```

計算每日速度損失。

**演算法：**
1. 取 calm condition（風力 ≤ 3, 浪高 ≤ 1m）的 STW 取中位數作為 **reference speed**
2. `speed_loss = reference_speed - actual_STW`
3. 正值 = 慢於基準（效能下降），負值 = 快於基準（正常）

**Response:**
```json
{
  "vessel_id": "S1",
  "reference_speed": 12.96,
  "avg_speed_loss_kn": -0.881,
  "calm_records_used": 464,
  "timeline": [
    {
      "noon_day": 0.0,
      "voyage": 28.0,
      "stw": 14.68,
      "ref_speed": 12.96,
      "speed_loss": -1.72,
      "wind_scale": 3.0,
      "sea_height": null
    }
  ]
}
```

---

### Speed Loss 歸因分析

```
GET /api/v1/vessels/{vessel_id}/speed-loss-attribution
```

將速度損失分解為 4 個來源。

**歸因模型（Heuristic）：**

| 來源 | 計算方式 |
|------|---------|
| `weather_loss` | 風力 × 0.04 + 浪高 × 0.08 |
| `hull_loss` | 距上次 DD（乾塢）天數 × 0.0005（上限 1.5 kn）|
| `propeller_loss` | ME_SLIP × 0.02 |
| `other_loss` | 固定 0.1 |

**Response:**
```json
{
  "vessel_id": "S1",
  "summary": {
    "weather_loss": 0.183,
    "hull_loss": 0.412,
    "propeller_loss": 0.201,
    "other_loss": 0.1,
    "total_loss": 0.896
  },
  "timeline": [
    {
      "noon_day": 0.0,
      "weather_loss": 0.12,
      "hull_loss": 0.0,
      "propeller_loss": 0.265,
      "other_loss": 0.1,
      "total_loss": 0.485
    }
  ]
}
```

---

### 維護事件紀錄

```
GET /api/v1/vessels/{vessel_id}/maintenance-events
```

回傳該船所有維護事件，依時間排序。

**事件類型說明：**

| 類型 | 說明 |
|------|------|
| `DD` | Dry Dock 乾塢 |
| `UWC` | Underwater Cleaning 水下清洗 |
| `PP` | Propeller Polishing 螺旋槳拋光 |
| `UWI` | Underwater Inspection 水下檢查 |
| `UWI+PP` | 水下檢查 + 螺旋槳拋光 |
| `UWC+PP` | 水下清洗 + 螺旋槳拋光 |

**Response:**
```json
{
  "vessel_id": "S1",
  "total": 5,
  "events": [
    {
      "vessel_id": "S1",
      "event_day": 981.0,
      "event_type": "DD",
      "propeller_condition": null,
      "hull_fouling_type": null,
      "hull_coating_condition": null,
      "cavitation_found": null,
      "draft_fwd_m": null,
      "draft_aft_m": null
    },
    {
      "vessel_id": "S1",
      "event_day": 1386.0,
      "event_type": "UWI+PP",
      "propeller_condition": null,
      "hull_fouling_type": "barnacle,slime,algae",
      "hull_coating_condition": "Good",
      "cavitation_found": null,
      "draft_fwd_m": 13.6,
      "draft_aft_m": 13.8
    }
  ]
}
```

---

### 維護建議

```
GET /api/v1/vessels/{vessel_id}/maintenance-recommendation
```

根據 ME slip 趨勢和距上次維護天數，給出建議。

**判斷邏輯：**
- `URGENT`：近 90 天平均 ME_SLIP > 10%，或距上次維護 > 365 天
- `ROUTINE`：其他情況
- `DD`：距上次維護 > 730 天（建議乾塢）
- `UWC`：其他（建議水下清洗）

**Response:**
```json
{
  "vessel_id": "S1",
  "days_since_maintenance": 21,
  "avg_me_slip_pct": 8.45,
  "recommendation": "ROUTINE",
  "recommended_type": "UWC",
  "reason": "Scheduled maintenance due (21 days since last event)",
  "last_maintenance": {
    "event_type": "UWI+PP",
    "event_day": 1804.0
  }
}
```

---

### 船隊排名

```
GET /api/v1/fleet/ranking
```

以 speed loss 排名訓練船（S1–S12）。排名越前 = 效能越好（損失越少）。

**Response:**
```json
{
  "total": 12,
  "fleet_ranking": [
    {
      "rank": 1,
      "vessel_id": "S3",
      "avg_speed_loss_kn": -2.14,
      "avg_me_slip_pct": 7.82,
      "avg_consumption_mt": 52.3,
      "records": 1521
    }
  ]
}
```

---

### 燃油消耗預測

```
POST /api/v1/predict/fuel-consumption
```

根據輸入的航行條件預測 ME 燃油消耗，並提供反事實分析（降速 1 kn 可省多少油）。

**模型：** Cubic Speed Least-Squares
- `consumption ≈ a × speed³ + weather_penalty`
- `a` 由各船歷史數據 least-squares 擬合
- `weather_penalty = wind_scale × 0.5 + sea_height × 0.8`

**Request Body:**
```json
{
  "vessel_id": "S1",
  "speed_kn": 15.0,
  "draft_fwd": 14.0,
  "draft_aft": 14.5,
  "cargo_on_board": 85000,
  "wind_scale": 3,
  "sea_height": 1.0
}
```

| 欄位 | 必填 | 說明 | 預設 |
|------|------|------|------|
| `vessel_id` | 否 | 使用哪艘船的模型 | S1 |
| `speed_kn` | 否 | 航行速度（節） | 15 |
| `draft_fwd` | 否 | 前吃水（m） | 14 |
| `draft_aft` | 否 | 後吃水（m） | 14 |
| `cargo_on_board` | 否 | 貨載量（噸） | 80000 |
| `wind_scale` | 否 | 蒲福風級（0–12） | 3 |
| `sea_height` | 否 | 浪高（m） | 1.0 |

**Response:**
```json
{
  "vessel_id": "S1",
  "input": {
    "speed_kn": 15.0,
    "draft_fwd": 14.0,
    "draft_aft": 14.5,
    "cargo_on_board": 85000.0,
    "wind_scale": 3.0,
    "sea_height": 1.0
  },
  "predicted_consumption_mt": 68.42,
  "model": "cubic_speed_lsq",
  "counterfactual": {
    "slow_by_1kn_speed": 14.0,
    "predicted_consumption_mt": 56.38,
    "fuel_saving_mt": 12.04,
    "saving_pct": 17.6
  }
}
```

---

## 錯誤格式

```json
{ "error": "Vessel S99 not found" }
```

| HTTP Code | 說明 |
|-----------|------|
| 400 | 參數錯誤 |
| 404 | 船舶不存在 |
| 500 | 伺服器內部錯誤 |

---

## 快速測試

```bash
BASE="https://4rh4qj5e3i.execute-api.us-east-1.amazonaws.com/dev"

# Health
curl $BASE/health

# 船舶列表
curl $BASE/api/v1/vessels

# S1 speed loss
curl $BASE/api/v1/vessels/S1/speed-loss

# S1 維護事件
curl $BASE/api/v1/vessels/S1/maintenance-events

# 船隊排名
curl $BASE/api/v1/fleet/ranking

# 燃油預測
curl -X POST $BASE/api/v1/predict/fuel-consumption \
  -H "Content-Type: application/json" \
  -d '{"vessel_id":"S1","speed_kn":16,"wind_scale":4,"sea_height":1.5}'
```
