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
| 船隊摘要（預計算） | `ship-analysis-dev-fleet-summary` | 15 筆（每船一筆，`build_fleet_summary.py` 產生，`/api/v1/fleet/summary` 用）|

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

`method: "ISO19030_FOC_normalized + STW_RPM_baseline"` — 題目指定的 FOC-based 方法為主指標，另附 ISO 19030 STW 驗證層。篩選條件（題目指定）：`WIND_SCALE ≤ 4`、`HOURS_FULL_SPEED ≥ 22`。

**Layer 1（FOC-based，主指標，`foc_summary`/`foc_timeline`）：**
1. `Daily FOC = ME_FULLSPEED_CONSUMP_{當日燃料} 依 LCV 換算 VLSFO 當量 ÷ HOURS_FULL_SPEED × 24`（跟主辦單位公式一致）
2. 依養護事件（`HULL_CLEAN_TYPES`：DD/UWC/UWC+PP）切出養護週期，每個週期取前段 calm 記錄的 RPM-bin median FOC 當 baseline
3. `speed_loss_pct = (實際FOC - baseline FOC) / baseline FOC × 100`（下限 0，不允許負的 speed loss）

**Layer 2（STW-based，ISO 19030 驗證層，`stw_summary`/`stw_timeline`）：** 同一組週期／RPM-bin baseline，改比較 STW：`speed_loss_pct = (baseline STW - 實際STW) / baseline STW × 100`

**Response（節錄）：**
```json
{
  "vessel_id": "S1",
  "method": "ISO19030_FOC_normalized + STW_RPM_baseline",
  "filter_criteria": { "wind_scale_max": 4, "hours_full_speed_min": 22 },
  "foc_summary": {
    "avg_daily_foc_vlsfo": 58.4,
    "avg_speed_loss_pct": 3.2,
    "baseline_foc_by_rpm": { "65": 55.1, "70": 60.3 },
    "valid_records": 1450,
    "total_records": 1482
  },
  "foc_timeline": [
    { "noon_day": 0.0, "voyage": 28.0, "rpm": 67.2, "stw": 14.68, "daily_foc_vlsfo": 56.05,
      "baseline_foc": 55.1, "speed_loss_pct": 1.7, "fuel_type": "VLSFO",
      "hours_full_speed": 23.0, "wind_scale": 3.0, "cargo_on_board": 91791.0,
      "load_condition": "laden", "maintenance_cycle": 0 }
  ],
  "stw_summary": { "avg_speed_loss_pct": 0.9, "baseline_stw_by_rpm": { "65": 14.51 }, "valid_records": 1420 },
  "stw_timeline": [
    { "noon_day": 0.0, "voyage": 28.0, "rpm": 67.2, "stw": 14.68, "ref_stw": 14.51,
      "speed_loss_pct": 0.0, "wind_scale": 3.0, "load_condition": "laden", "maintenance_cycle": 0 }
  ],
  "maintenance_cycles": [
    { "cycle_index": 0, "start_day": 0.0, "end_day": 980.0, "trigger_event": null,
      "records": 188, "baseline_foc_avg": 52.1, "end_foc_avg": 61.3, "degradation_pct": 17.7 }
  ]
}
```

| 欄位 | 說明 |
|------|------|
| `load_condition` | `laden`／`ballast`，依 `CARGO_ON_BOARD` 對船型（W1/W2）門檻值判定 |
| `maintenance_cycles[].degradation_pct` | 該養護週期從開始到結束，FOC 劣化幅度（%），`trigger_event` 是觸發該週期開始的事件類型 |

---

### Speed Loss 歸因分析

```
GET /api/v1/vessels/{vessel_id}/speed-loss-attribution
```

`method: "fleet_calibrated_degradation_rate"` — 用**艦隊校準的劣化速率**分開估算船殼、螺旋槳的貢獻，取代早期「事件前後 ±30 天快照平均」的做法。

**為什麼不是直接比較事件前後的原始資料**：單一事件、單一船的 before/after 快照，會被天候、載重、清潔後試俥等短期操作雜訊嚴重污染——實測過三種改法（天候篩選、RPM 配對、週期邊界快照），「清潔後效能反而變差」這種違反物理常識的比例都還停在 40–60% 區間。真正乾淨的訊號來自把全船隊資料 pool 起來做迴歸：單一船單一週期的 R² 只有 ~0.07（雜訊蓋過趨勢），但把所有訓練船（S1–S12）的資料一起 pool（n>3000）後，兩個通道的劣化速率都達到統計顯著。

**船殼跟螺旋槳用不同物理量，不是同一個滑差硬套兩種東西**：

| 通道 | 指標 | 為什麼 |
|---|---|---|
| 船殼 | Daily FOC（跟 `/speed-loss` Layer 1 同一套，VLSFO 當量）| 船殼阻力的直接訊號是「同轉速下要燒更多油」|
| 螺旋槳 | `FULL_SPD_STW_SLIP` | 滑差＝螺旋槳理論前進 vs 實際前進的差，本質就是螺旋槳效率指標 |

（早期版本兩個通道都用滑差校準，物理上是錯的——滑差對船殼阻力只是間接、微弱的訊號。）

**艦隊校準（`_fleet_degradation_rates()`，快取，啟動時預熱）：**

1. 船殼：取 calm condition（`WIND_SCALE≤4`、`HOURS_FULL_SPEED≥22`）的 Daily FOC；螺旋槳：同條件的 `FULL_SPD_STW_SLIP`
2. 依事件類型切出兩種獨立週期：船殼週期（邊界＝`DD`/`UWC`/`UWC+PP`）、螺旋槳週期（邊界＝`DD`/`PP`/`UWI+PP`/`UWC+PP`）
3. 每個週期以自己的 baseline（前 ~15%）置中——船殼是「相對 baseline 的 % 變化」（跨船/跨燃料量級不同，正規化成相對值），螺旋槳是「相對 baseline 的百分點差」（滑差本身已經是 %，量級可比）——把「週期內第幾天」vs 置中後的值，跨全部訓練船 pool 起來做線性迴歸
4. 斜率（%/30天）即為船隊平均劣化速率；目前實測約：船殼 **0.71%/30天**（t≈8，speed-loss %，換算成一個典型 ~28個月週期約 20%，跟命題簡報提到的「船殼嚴重時影響效能可能超過20%」量級吻合）、螺旋槳 **0.083%/30天**（t≈6，滑差百分點），兩者都遠超過 `|t|>2` 顯著性門檻

**單船事件歸因**：船殼——`slip_after_pct` 固定 `0.0`（清潔後即為該週期自己的基準，定義上是 0%），`slip_before_pct` = 船殼速率 × 距上次船殼清潔累積天數（模型推論的 speed-loss %）。螺旋槳——`slip_after_pct` 是清潔後新週期的**實際觀測**滑差 baseline，`slip_before_pct` = 該值 + 螺旋槳速率 × 累積天數。兩者 `slip_delta_pct = slip_before_pct - slip_after_pct`，恆為非負。`DD`/`UWC+PP` 套用船殼+螺旋槳（category `hull+propeller`）；`UWC` 只套船殼；`PP`/`UWI+PP` 只套螺旋槳；`UWI`（純檢查，無物理介入）不套用任何速率，`before`/`after`/`delta` 皆為 `null`。**`metric` 欄位標示這筆數字實際單位**（`speed_loss_pct_foc` 或 `slip_pct_points`），不要當成同一種量直接比較。

**Response:**
```json
{
  "vessel_id": "S1",
  "method": "fleet_calibrated_degradation_rate",
  "fleet_calibration": {
    "hull":      { "slope_per_30d_pct": 0.7126, "t_stat": 7.84, "n_records": 3725, "significant": true,
                    "metric": "speed_loss_pct_foc_relative_to_cycle_baseline" },
    "propeller": { "slope_per_30d_pct": 0.0826, "t_stat": 5.94, "n_records": 3645, "significant": true,
                    "metric": "full_spd_stw_slip_pct_points" },
    "calibrated_on_vessels": 12,
    "method": "pooled_linear_regression_vs_days_since_cleaning"
  },
  "summary": {
    "hull+propeller": 23.3,
    "propeller": 0.57
  },
  "event_attributions": [
    {
      "event_type": "DD",
      "event_day": 981.0,
      "category": "hull+propeller",
      "physical_intervention": true,
      "metric": "speed_loss_pct_foc",
      "slip_before_pct": 23.3,
      "slip_after_pct": 0.0,
      "slip_delta_pct": 23.3,
      "notes": "Fleet-rate-modeled improvement: +23.30% (speed_loss_pct_foc)"
    },
    {
      "event_type": "UWI+PP",
      "event_day": 1386.0,
      "category": "propeller",
      "physical_intervention": true,
      "metric": "slip_pct_points",
      "slip_before_pct": 9.26,
      "slip_after_pct": 8.14,
      "slip_delta_pct": 1.12,
      "notes": "Fleet-rate-modeled improvement: +1.12% (slip_pct_points)"
    }
  ],
  "weather_timeline": [
    { "noon_day": 0.0, "diff_stw_sog": 0.42 }
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
  "avg_consumption_mt": 58.4,
  "degradation_rate_pct_per_day": 0.0032,
  "fuel_price_usd_per_mt": 620,
  "recommendation": "ROUTINE",
  "recommended_type": "UWC",
  "reason": "Scheduled maintenance due (21 days since last event)",
  "last_maintenance": {
    "event_type": "UWI+PP",
    "event_day": 1804.0
  },
  "curve": [
    { "deferral_days": 0, "projected_slip_pct": 8.45, "cumulative_excess_fuel_cost_usd": 583.2 }
  ]
}
```

| 欄位 | 說明 |
|------|------|
| `degradation_rate_pct_per_day` | 近 90 天 vs 前 90 天平均 slip 的變化率，用來推算未來衰退曲線 |
| `curve` | 未來 91 天（0–90 天）若不維護，累積超耗油成本的推算曲線，`cumulative_excess_fuel_cost_usd = Σ avg_consumption_mt × (projected_slip_pct/100) × 1.8 × fuel_price_usd_per_mt` |

---

### 船隊排名

```
GET /api/v1/fleet/ranking
```

以 `FULL_SPD_STW_SLIP`（0–30% 有效值）平均排名訓練船（S1–S12）。`avg_slip_pct` 越低 = 效能越好，排名越前。

**Response:**
```json
{
  "total": 12,
  "fleet_ranking": [
    {
      "rank": 1,
      "vessel_id": "S3",
      "avg_slip_pct": 7.82,
      "recent_90d_slip_pct": 7.4,
      "slip_trend": -0.42,
      "avg_consumption_mt": 52.3,
      "valid_slip_records": 1490,
      "total_records": 1521
    }
  ]
}
```

| 欄位 | 說明 |
|------|------|
| `recent_90d_slip_pct` | 最近 90 筆有效 slip 資料的平均 |
| `slip_trend` | `recent_90d_slip_pct - avg_slip_pct`，正值 = 近期比全期均值差（效能在衰退）|

---

### 船隊摘要（Dashboard 用）

```
GET /api/v1/fleet/summary
```

單次呼叫回傳整個船隊（15 艘）的彙總 KPI + 逐船摘要，給 Dashboard 總覽頁用。優先讀 `ship-analysis-dev-fleet-summary` 表（`build_fleet_summary.py` 預計算寫入，啟動時預熱）；該表讀取失敗或為空時才即時用 DynamoDB 原始資料現算（欄位較少）；若連現算都對全部船失敗（例如憑證過期），回傳 `502` 而非假裝資料是空的 `200`。

**Response（節錄）：**
```json
{
  "total_vessels": 15,
  "training_vessels": 12,
  "prediction_vessels": 3,
  "pending_maintenance": 4,
  "avg_fleet_slip_pct": 8.1,
  "total_excess_fuel_cost_usd_per_day": 3120.5,
  "worst_vessel": { "vessel_id": "S7", "avg_slip_pct": 12.3, "urgency": "HIGH" },
  "per_vessel": [
    {
      "vessel_id": "S1", "type": "training", "ship_class": "W1",
      "avg_slip_pct": 8.12, "recent_90d_slip_pct": 7.9, "slip_trend": -0.22,
      "avg_consumption_mt": 58.4, "urgency": "MEDIUM",
      "days_since_maintenance": 21, "days_since_hull_clean": 21, "days_since_prop_polish": 21,
      "excess_fuel_cost_usd_per_day": 583.2,
      "lat": 24.1, "lon": 121.7, "heading_deg": 88.0, "speed_kt": 14.2,
      "total_records": 1482, "total_voyages": 22, "rank": 3
    }
  ]
}
```

`urgency`（`LOW`/`MEDIUM`/`HIGH`）：`recent_90d_slip_pct`（或退回 `avg_slip_pct`）≥10 或距上次維護>365天 → `HIGH`；≥6 或 >270天 → `MEDIUM`；其餘 `LOW`。`excess_fuel_cost_usd_per_day = avg_consumption_mt × (slip%/100) × 1.8 × 620`（VLSFO 假設單價 USD 620/噸）。

---

### 燃油消耗預測

```
POST /api/v1/predict/fuel-consumption
```

使用 XGBoost 模型（`model_v3.pkl`）預測指定船舶在特定天的主機全速油耗（MT/day），並自動計算「如果現在執行 UWC+PP 能節省多少」的反事實推論。

**模型說明：** XGBoost v3 Hybrid（600 棵樹）
- 29 個特徵，含環境、航行條件、船體污損退化（`days_since_hull_clean`、`days_since_prop_polish`）
- `physics_consumption = ship_coefficient / stw²` 作為物理基線特徵
- `UWI`（純檢查）不重置污損計時，符合題目要求

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
    "WIND_SCALE": 6,
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

**Response:**

```json
{
  "vessel_id": "S21",
  "noon_day":  136.0,
  "model":     "xgboost_v3_hybrid",
  "input_used": {
    "avg_speed_kn":           10.6,
    "stw_kn":                 10.6,
    "wind_scale":             4.0,
    "sea_height":             1.0,
    "fore_draft":             12.45,
    "aft_draft":              12.45,
    "hours_full_speed":       25.0,
    "days_since_hull_clean":  2.0,
    "days_since_prop_polish": 2.0
  },
  "predicted_consumption_mt": 52.3,
  "counterfactual_uwc_pp": {
    "description":              "Predicted consumption if UWC+PP were performed now (days_since=0)",
    "predicted_consumption_mt": 49.8,
    "fuel_saving_mt_per_day":   2.5,
    "saving_pct":               4.8,
    "est_annual_saving_mt":     750.0,
    "est_annual_saving_usd":    450000.0
  }
}
```

| 欄位 | 說明 |
|------|------|
| `input_used.days_since_hull_clean` | 截至 `noon_day`，距最後一次船殼清洗（UWC/DD）的天數 |
| `input_used.days_since_prop_polish` | 截至 `noon_day`，距最後一次螺旋槳拋光（PP/DD）的天數 |
| `predicted_consumption_mt` | 當前狀態預測油耗（MT/day）|
| `counterfactual_uwc_pp.fuel_saving_mt_per_day` | 執行 UWC+PP 後每日可節省油耗（MT/day）|
| `counterfactual_uwc_pp.est_annual_saving_usd` | 估算年節省金額（300 海上天/年 × $600/MT）|
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
BASE="https://d1yvzz0da29zvi.cloudfront.net"   # 生產。本機測試改用 http://localhost:8000

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

# 船隊摘要（Dashboard 總覽用）
curl $BASE/api/v1/fleet/summary

# 燃油預測 — noon_day lookup（推薦）
curl -X POST $BASE/api/v1/predict/fuel-consumption \
  -H "Content-Type: application/json" \
  -d '{"vessel_id":"S21","noon_day":136}'

# 燃油預測 — what-if（override 風浪條件）
curl -X POST $BASE/api/v1/predict/fuel-consumption \
  -H "Content-Type: application/json" \
  -d '{"vessel_id":"S21","noon_day":960,"WIND_SCALE":6,"SEA_HEIGHT":2.5}'
```
