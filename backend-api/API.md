# Ship Performance Analysis API

**Base URL (CloudFront):** `https://d1yvzz0da29zvi.cloudfront.net`

**Base URL (EC2 direct):** `http://52.45.130.183:8000`

**架構：** CloudFront → EC2 (ECS, EC2 launch type) → Docker container (FastAPI + XGBoost) → DynamoDB

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

使用 `model_v5_final.pkl` 預測指定船舶在特定天的 **VLSFO 等效、24 小時標準化主機日耗**（MT/24h），並計算 UWC+PP 反事實情境下的能源成本差額。

**模型說明：** v5 XGBoost + LightGBM 50:50 ensemble
- 30 個特徵，含 RPM、航速／航程、吃水／載重、海象、維護狀態與 ISO 19030 FOC speed loss
- 預測目標統一為 `各油種耗量 × LCV / VLSFO LCV / HOURS_FULL_SPEED × 24`
- 訓練適用範圍：`WIND_SCALE ≤ 4` 且 `HOURS_FULL_SPEED ≥ 22`；不符合時 API 回傳 HTTP 422，不產生不可靠的預測
- UWC+PP 反事實假設：最近維護天數設為 0、維護類型設為 UWC+PP，並將 FOC speed loss 設為 0

---

#### 使用方式一：noon_day lookup（推薦）

只需傳 `vessel_id` + `noon_day`，API 自動從資料庫撈該天的航行資料並計算所有 features。

```bash
curl -X POST $BASE/api/v1/predict/fuel-consumption \
  -H "Content-Type: application/json" \
  -d '{"vessel_id": "S21", "noon_day": 136}'
```

#### 使用方式二：欄位 override（what-if 情境）

在 noon_day 基礎上，額外覆蓋任何 A 類欄位，模擬不同條件。

```bash
curl -X POST $BASE/api/v1/predict/fuel-consumption \
  -H "Content-Type: application/json" \
  -d '{
    "vessel_id":  "S21",
    "noon_day":   960,
    "WIND_SCALE": 4,
    "SEA_HEIGHT": 2.5
  }'
```

**可 override 的欄位（對應 vt_fd.csv 欄位名稱）：**

| 欄位 | 說明 | 單位 |
|------|------|------|
| `AVG_SPEED` | 對地航速（SOG）| knots |
| `SPEED_THROUGH_WATER` | 對水航速（STW）| knots |
| `WIND_SCALE` | 蒲福風級 | 0–12 |
| `WIND_SPEED` | 風速 | knots |
| `SEA_HEIGHT` | 浪高 | m |
| `SWELL_HEIGHT` | 湧浪高度 | m |
| `SEA_WATER_TEMP` | 海水溫度 | °C |
| `WATER_DEPTH` | 水深 | m |
| `FORE_DRAFT` | 首吃水 | m |
| `AFTER_DRAFT` | 尾吃水 | m |
| `MID_DRAFT` | 舯吃水 | m |
| `HOURS_FULL_SPEED` | 全速航行時數 | hr |
| `DIFF_STW_SOG_SLIP` | 對水-對地速差 | knots |
| `FULL_SPD_STW_SLIP` | 全速時段滑差 | % |
| `fuel_type` | 油種欄位名；若未提供會從 `noon_day` 日報推斷，仍無法判定時預設 VLSFO | enum |

支援來源油種：`ME_FULLSPEED_CONSUMP_HSHFO`、`ME_FULLSPEED_CONSUMP_VLSFO`、`ME_FULLSPEED_CONSUMP_ULSFO`、`ME_FULLSPEED_CONSUMP_LSMGO`、`ME_FULLSPEED_CONSUMP_BIO_HSFO`。請求的 `fuel_type` 僅用來標示 `source_fuel_type` 的可追溯來源；v5 輸出、反事實節省與能源成本均固定為 VLSFO 等效 24 小時基準，並在 `input_used.fuel_type` 明確回傳 VLSFO。未指定時，API 會從日報推斷單一或混合來源油種。

**Response:**

```json
{
  "vessel_id": "S21",
  "noon_day": 136.0,
  "model": "v5_xgboost_lightgbm_ensemble",
  "input_used": {
    "avg_speed_kn": 10.6,
    "stw_kn": 10.6,
    "wind_scale": 4.0,
    "sea_height": 1.0,
    "fore_draft": 12.45,
    "aft_draft": 12.45,
    "hours_full_speed": 25.0,
    "days_since_hull_clean": 2.0,
    "days_since_prop_polish": 2.0,
    "fuel_type": "ME_FULLSPEED_CONSUMP_VLSFO",
    "fuel_type_source": "v5_model_basis",
    "source_fuel_type": "ME_FULLSPEED_CONSUMP_VLSFO",
    "source_fuel_type_source": "noon_report",
    "effective_fuel_lcv_mj_per_kg": 40.2,
    "prediction_basis": "VLSFO_equivalent_24h",
    "model_applicability": { "wind_scale_max": 4, "hours_full_speed_min": 22 }
  },
  "predicted_consumption_mt": 52.3,
  "counterfactual_uwc_pp": {
    "description": "v5 VLSFO-equivalent 24h prediction if UWC+PP were performed now (maintenance age and FOC speed loss reset)",
    "predicted_consumption_mt": 49.8,
    "fuel_saving_mt_per_day": 2.5,
    "raw_fuel_delta_mt_per_day": 2.5,
    "benefit_available": true,
    "saving_pct": 4.8,
    "est_annual_saving_mt": 750.0,
    "energy_pricing": {
      "fuel_type": "ME_FULLSPEED_CONSUMP_VLSFO",
      "source_lcv_mj_per_kg": 40.2,
      "normalized_energy_gj_per_day": 100.5,
      "diesel_equivalent_l_per_day": 2801.96,
      "price_twd_per_litre": 28.8,
      "daily_saving_twd": 80696,
      "annual_saving_twd": 24208764,
      "sea_days_per_year": 300,
      "price_source": {
        "name": "Taiwan CPC public retail diesel price",
        "effective_date": "7月13日",
        "status": "fetched",
        "basis": "CPC super diesel retail price is an open-data energy-price proxy, not a bunker spot quote."
      }
    }
  }
}
```

| 欄位 | 說明 |
|------|------|
| `input_used.days_since_hull_clean` | 截至 `noon_day`，距最後一次船殼清洗（UWC/DD）的天數 |
| `input_used.days_since_prop_polish` | 截至 `noon_day`，距最後一次螺旋槳拋光（PP/DD）的天數 |
| `input_used.fuel_type` / `fuel_type_source` | v5 固定使用的 VLSFO 等效模型／計價基準 |
| `input_used.source_fuel_type` / `source_fuel_type_source` | 原始 request 或日報油種來源，僅供可追溯性，不改變 v5 的 VLSFO 等效預測或價格計算 |
| `input_used.effective_fuel_lcv_mj_per_kg` | v5 的預測與節省統一採 VLSFO 等效基準，因此為 VLSFO LCV（40.2 MJ/kg） |
| `input_used.prediction_basis` | 固定為 `VLSFO_equivalent_24h`；所有 `predicted_consumption_mt` 與節省 MT 皆為 VLSFO 等效 24 小時量 |
| `input_used.model_applicability` | v5 的穩態訓練條件；超出時 API 回傳 422 |
| `predicted_consumption_mt` | 當前狀態預測油耗（MT/day）|
| `counterfactual_uwc_pp.raw_fuel_delta_mt_per_day` | 原始模型差值，可為負值，供診斷使用 |
| `counterfactual_uwc_pp.benefit_available` | 原始差值是否大於 0；false 時節省量與金額皆為 0 |
| `counterfactual_uwc_pp.fuel_saving_mt_per_day` | 僅計正向的每日節省油耗（MT/day）|
| `counterfactual_uwc_pp.energy_pricing` | 先依有效 LCV 將節省 MT 折算為 GJ，再換算柴油等值公升，乘台灣中油公開超級柴油牌價得 TWD 金額；`price_source.status` 為 fetched 或 fallback |

> 此金額是可追溯的能源成本節省估計，不是完整財務 ROI 比率；目前資料集沒有清洗費、進塢費或停航機會成本。中油柴油零售價是公開能源價格代理，不等於船用 bunker spot quote。
>
> Beta API 已以 `energy_pricing` 取代舊的固定 `est_annual_saving_usd`。不保留固定 USD 欄位，避免繼續使用無公開價格依據的 `$600/MT` 假設。

---

## 錯誤格式

```json
{ "error": "Vessel S99 not found" }
```

| HTTP Code | 說明 |
|-----------|------|
| 400 | 參數錯誤 |
| 404 | 船舶不存在 |
| 422 | 請求超出 v5 訓練適用範圍（風級 >4 或全速時數 <22） |
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

# 燃油預測 — noon_day lookup（推薦）
curl -X POST $BASE/api/v1/predict/fuel-consumption \
  -H "Content-Type: application/json" \
  -d '{"vessel_id":"S21","noon_day":136}'

# 燃油預測 — what-if（override 風浪條件）
curl -X POST $BASE/api/v1/predict/fuel-consumption \
  -H "Content-Type: application/json" \
  -d '{"vessel_id":"S21","noon_day":960,"WIND_SCALE":6,"SEA_HEIGHT":2.5}'
```
