# API 串接對應表（Frontend ↔ Backend）

> 給前端工程師看的串接清單。彙整自 `backend/app/routers/*.py`（實際已實作的 4 支 API）
> 與 `design_docs/1_fleet-dashboard-frontend-requirements.md` 第 6 節（前端頁面預期資料形狀）。
> Base URL（本機開發）：`http://127.0.0.1:8000`

---

## 現況總覽

後端目前只有 **4 支真實 API**，全部是「單船 (`{vessel}`)」層級，沒有船隊層級的
彙總 API（列表、地圖、KPI 卡）。前端目前這些部分是用 `frontend/src/mock/api.ts`
的假資料撐著（`fetchFleetKpis`、`fetchFleetVessels`、`fetchInspections`、
`fetchFuelAttribution` 皆為 mock，後端無對應端點）。

| 後端 API | 對應前端頁面 | 狀態 |
|---|---|---|
| ① `GET /api/v1/vessels/{vessel}/performance-trend` | `/vessels/:imo/speed-loss` | ✅ 可串接 |
| ② `GET /api/v1/vessels/{vessel}/maintenance-effectiveness` | `/vessels/:imo/speed-loss`（比較清洗週期）、`/vessels/:imo/maintenance-advisor` | ✅ 可串接 |
| ③ `GET /api/v1/vessels/{vessel}/anomalies` | `/vessels/:imo/noon-reports`（異常標記列） | ✅ 可串接 |
| ④ `GET /api/v1/vessels/{vessel}/maintenance-recommendation` | `/vessels/:imo/maintenance-advisor` | ✅ 可串接 |
| — | `/`（船隊總覽）、`/vessels`（船隊列表） | ❌ 無後端 API，仍用 mock |
| — | `/vessels/:imo/inspections`（水下檢查報告） | ❌ 無後端 API，仍用 mock |
| — | `/vessels/:imo/fuel-attribution`（油耗歸因瀑布圖） | ❌ 無後端 API，仍用 mock |
| — | `/fleet-analytics`（跨船隊比較） | ❌ 無後端 API，仍用 mock |

---

## 詳細對應

### ① 效能趨勢分析
```
GET /api/v1/vessels/{vessel}/performance-trend?start_date=&end_date=
```
- **對應頁面**：`/vessels/:imo/speed-loss`（4.6 Speed Loss 互動分析）
- **對應元件**：主圖表（時間序列折線/散點）、坐塢/清潔事件垂直虛線標記
- **對應 mock 函式**：`fetchSpeedLoss(imo)`（`frontend/src/mock/api.ts`）— 欄位需重新映射，見下方注意事項
- **回傳** `series[]`：`date`、`speed_loss_pct`、`me_power_kw`、`sfoc_gkwh`、`event`（`"Hull Cleaning"` 或 null）
- **注意事項**：
  - 後端沒有 `observedSpeed`、`correctedSpeed`、`loadCondition`、`beaufort`、`fuelConsumptionMt`、`isAnomaly` 這些欄位（design doc 第 6 節列的形狀），目前只給 `speed_loss_pct` + `me_power_kw` + `sfoc_gkwh`。若要支援「海況篩選 Beaufort ≤ 3」「Ballast/Laden 切換」等互動控制項，需要後端補欄位，或前端改用 Noon Report 原始資料自行 join。
  - `event` 目前只有 `"Hull Cleaning"`，沒有 `propeller_polishing` 的清潔類型區分，若要在圖上標不同顏色的事件線，需跟後端確認能否擴充。

### ② 維修效益驗證
```
GET /api/v1/vessels/{vessel}/maintenance-effectiveness
GET /api/v1/vessels/{vessel}/maintenance-effectiveness/{event_date}
```
- **對應頁面**：
  - `/vessels/:imo/speed-loss` 的「比較上次清洗週期」按鈕（4.6 互動控制項）
  - `/vessels/:imo/maintenance-advisor` 的歷史維修效益佐證（4.8 建議卡的信心程度依據）
- **對應元件**：清洗前後對比卡（before/after Speed Loss、回本天數）
- **回傳**：`speed_loss_before_pct`、`speed_loss_after_pct`、`speed_recovery_kt`、`daily_foc_saving_mt`、`est_annual_fuel_saving_usd`、`maintenance_cost_usd`、`payback_days`、`effectiveness_note`（白話說明，可直接當 tooltip 文字）、`supporting_uwi_note`
- **注意事項**：清單版（不帶 `event_date`）一次回傳該船所有維修事件，適合「比較上次清洗週期」的資料來源；單一事件版可用於點擊某個坐塢事件後的詳情彈窗。

### ③ 異常預警與成因分類
```
GET /api/v1/vessels/{vessel}/anomalies?z_threshold=&start_date=&end_date=&use_llm=
```
- **對應頁面**：`/vessels/:imo/noon-reports`（4.4 異常值標記為 `--signal-red` 底色的那一列）
- **對應元件**：Noon Report 表格列的異常 hover 說明（design doc 要求「hover 顯示判定原因」）
- **回傳** `anomalies[]`：`date`、`speed_loss_pct`、`z_score`、`rule_based_cause`（規則判定原因，可直接當 hover 文字）、`llm_hypothesis`（LLM 補位推測，規則判不出來時才有值）、`urgency`
- **對應 mock 函式**：目前 `NoonReports.vue` 用的是 `fetchNoonReports(imo)` 內建的 `isAnomaly` 布林值，需改為：先打 Noon Report 資料來源（目前也無獨立後端 API，見下方缺口），再用這支 API 回傳的 `date` 清單去比對哪幾列要標紅、並把 `rule_based_cause` / `llm_hypothesis` 塞進 hover tooltip。

### ④ 最佳維修時機建議
```
GET /api/v1/vessels/{vessel}/maintenance-recommendation?as_of_date=
```
- **對應頁面**：`/vessels/:imo/maintenance-advisor`（4.8 維修時機建議，核心資料來源）
- **對應元件**：建議卡（action / 建議日期 / 信心程度）、`recommendation_note` 可直接當「未盡之處」旁的白話說明
- **回傳**：`current_speed_loss_pct`、`degradation_rate_pct_per_day`、`est_hull_cleaning_cost_usd`、`breakeven_days_from_now`、`maintenance_urgency`、`baseline_fallback_used`、`recommendation_note`
- **注意事項**：
  - design doc 4.8 要求的「成本效益模擬曲線」（延後天數 vs. 累積超額油耗成本 vs. 機會成本，兩條線疊圖）後端**沒有**回傳曲線資料點陣列，只回傳單一 `breakeven_days_from_now` 數值。目前前端 mock 的 `curve[]`（`fetchMaintenanceRecommendation`）是自己模擬生成的，串真實 API 後這條核心曲線圖會沒有資料，需要跟後端確認是否要擴充 API 回傳逐日曲線，或前端改成只呈現單點式建議（不畫雙線交叉圖）。
  - `windowStart` / `windowEnd`（建議執行區間）後端沒有，只有 `breakeven_days_from_now`（單一天數），前端需自行從 `as_of_date + breakeven_days_from_now` 往前後各推算幾天做區間，或跟後端確認是否補這個欄位。

---

## 目前沒有後端 API、仍需用 mock 頂著的頁面

| 頁面 | 缺口說明 |
|---|---|
| `/`（船隊總覽） | 需要「船隊層級 KPI」「所有船目前位置」的彙總 API，後端目前僅支援單船查詢 |
| `/vessels`（船隊列表） | 需要「所有船清單 + 各船摘要（Speed Loss、狀態燈、下次維修窗口）」的彙總 API；`GET /api/v1/vessels` 目前只回傳船名字串陣列，沒有其他欄位 |
| `/vessels/:imo/noon-reports` | 需要 Noon Report 原始資料本身的 API（日期、位置、觀測/修正後航速、油耗、海況、吃水、Ballast/Laden），目前只有③異常清單，沒有完整 Noon Report 列表端點 |
| `/vessels/:imo/inspections` | 需要 UWI 檢查報告列表 API（污損分級、船體分區、照片、PDF），後端 `data.py` 有讀 `UWI_Inspections.csv`（②效益驗證內部用來找 `supporting_uwi_note`），但沒有對外開放列表端點 |
| `/vessels/:imo/fuel-attribution` | 需要油耗歸因（天氣/船體/螺旋槳/主機老化拆解）API，後端完全沒有這個邏輯，目前④的建議只給單一劣化速率，不含分因子拆解 |
| `/fleet-analytics` | 需要跨船隊排名/比較 API |

---

## 給前端工程師的建議串接順序

1. 先串 **①效能趨勢分析** → Speed Loss 主圖表可以先跑起來（最貼近後端現有能力）
2. 再串 **④最佳維修時機建議** → Maintenance Advisor 建議卡（但曲線圖需先跟後端對齊資料契約，見上方注意事項）
3. 再串 **③異常預警** → Noon Report 頁面的異常標記/hover（但列表本身仍需 mock 或另外談 API）
4. 再串 **②維修效益驗證** → Speed Loss 頁「比較清洗週期」+ Maintenance Advisor 信心佐證
5. 船隊總覽、船隊列表、檢查報告、油耗歸因、跨船隊分析：**先維持 mock**，待後端補齊對應端點後再換線
