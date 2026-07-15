# Design Tasks — 船舶養護核心價值呈現

## 0. 目標與核心價值主張

> 船隻航行中，Speed Loss 和油耗本就會隨時間持續成長（船體/螺旋槳附著物累積），但成長到什麼程度就不能忍受、必須進塢養護？養護後這兩個指標會重置並重新開始爬升——這個「爬升 → 門檻 → 養護 → 重置」的週期，就是白板圖要表達的核心敘事。

Speed Loss 與油耗是判斷「該不該養護」的兩個指標，但油耗還多一層價值：它可以換算成錢，回答「現在養護 vs. 拖到之後養護，具體省下多少油耗、多少美金」，也就是導入本系統後的 ROI。目前系統把這兩件事拆得很開，且油耗的「合併呈現」是用前端公式假造的，沒有真正打通。以下任務把現有頁面重新收斂成這個核心敘事，並補上「申請養護」的工作流程與「每日填報 + 即時觸發判斷」的輸入口。

## 現況盤點（先講清楚，才知道每個任務改動多大）

| 項目 | 現況 | 檔案 |
|---|---|---|
| Speed Loss 圖 | 獨立頁面，有真實回歸線 + 維修事件 markLine | `frontend/src/views/vessel/SpeedLoss.vue`，`GET /api/v1/vessels/{id}/speed-loss` |
| 油耗呈現 | 只有表格數字（Noon Report 表、What-if 預測圖），沒有隨時間變化的趨勢圖 | `frontend/src/views/vessel/NoonReports.vue`、`FuelPrediction.vue` |
| 唯一「合併」的圖 | `MaintenanceCorrelation.vue` 的時間軸圖同時畫 Speed Loss % 與油耗，**但油耗數值是前端公式 `avgConsumption × (1 + slip%/100 × 1.8)` 算出來的，不是後端真實 `ME_CONSUMPTION`** | `MaintenanceCorrelation.vue:22,50,219` |
| 養護狀態 | 型別定義了 4 態，但只用到 2 態，且完全沒有寫入路徑，`maintenanceStatus` 沒有任何畫面真正渲染它 | `frontend/src/types/fleet.ts:11`、`frontend/src/api/adapter.ts:554` |
| 養護請求 API | **完全不存在**。目前後端所有 API 都是唯讀，沒有任何 `POST/PATCH` 寫入 DynamoDB 的程式碼 | `backend-api/handler.py`（全檔案搜尋 `put_item` 零命中） |
| Noon Report 填報 | 唯讀表格，資料來自比賽提供的靜態 CSV，沒有上傳/新增介面或 API | `NoonReports.vue`、`vt_fd.csv` |
| 閥值/預警 | 只有 `MaintenanceCorrelation.vue` 裡一組前端 slider（門檻 %、預警天數），**純前端 state，重新整理就消失，從沒送到後端** | `MaintenanceCorrelation.vue:24-31,116-135` |
| ROI 計算基礎 | 已經存在！`get_maintenance_recommendation` 端點已經用 `FUEL_PRICE=620 USD/MT` 算出「延後養護的累積超額油耗成本曲線」，但沒有跟「建議進塢時間點」串起來，也沒有換算成「現在做 vs. 現在不做」的省多少錢卡片 | `backend-api/handler.py:581-657` |
| 權限/角色 | 全專案沒有登入、沒有角色概念，「岸上管理員」目前等同於任何打開網站的人 | 全域搜尋 auth/role/admin 零命中 |

**⚠️ 風險警示（對應需求 0）**：把 Speed Loss 與油耗真正整合成一張「用真實資料算出來的」趨勢圖，**不是小改動**。原因：
1. 目前油耗沒有任何「隨時間的趨勢/回歸」計算（Speed Loss 有，油耗沒有），需要新寫一套邏輯，而不是重用現成的。
2. 要標示「建議進塢時間點」，需要一套門檻外推演算法（目前完全不存在，只有前端 slider 是假的）。
3. 需要修掉 `MaintenanceCorrelation.vue` 裡油耗造假公式，牽動既有頁面。

這塊我拆成 Task 1，並建議**優先做**，因為後面幾個任務（每日填報的即時判斷、ROI 卡片）都要依賴它算出來的門檻邏輯，不想在多處重複造輪子。

---

## 任務總覽

| # | 任務 | 對應需求 | 前端 | 後端 | 預估時間（AI vibe coding） | 相依 |
|---|---|---|---|---|---|---|
| 1 | 船舶健康趨勢圖：整合 Speed Loss + 真實油耗 + 進塢建議標記 | 0、3 | ✅ 新元件 | ✅ 新端點 | **6–9 hr**（⚠️ 中大幅度） | 無 |
| 2 | 提交養護工單申請 | 1 | ✅ | ✅ 新端點（首個寫入 API） | 3–4 hr | 無，但建議先做 |
| 3 | 養護狀態顯示與推進（4 態） | 2 | ✅ | ✅ 擴充 Task 2 | 3–4 hr | Task 2 |
| 4 | 每日 Noon Report 填報 + 即時閥值檢查 | 4 | ✅ | ✅ 新端點 | 5–6 hr | Task 1（門檻邏輯）、Task 2（CTA 連動） |
| 5（加碼） | 節能效益 / ROI 卡片 | 呼應你說的「換算油價=ROI」 | ✅ 小元件 | ✅ 小擴充 | 2–3 hr | Task 1 |

**總計約 19–26 hr**，若照 1 → 2 → 3 → 4 → 5 的順序做，每個任務做完都是可獨立展示的成果。

---

## Task 1：船舶健康趨勢圖（核心價值視覺化）

**對應需求 0 + 3。** 就是白板圖：橫軸時間，兩條線（Speed Loss、油耗）隨時間爬升，遇到維修事件（垂直線）就重置，並標出「建議進塢養護」的時間點/區間。

### 為什麼是中大幅度改動
- 油耗目前沒有回歸/趨勢計算，要仿照 Speed Loss 端點現有的回歸邏輯（`handler.py:353-454`）另寫一套，並依維修事件切段（segment）分別算。
- 「建議進塢時間點」需要新的外推演算法：用目前的成長率（degradation rate，`get_maintenance_recommendation` 已有類似算法可參考 `handler.py:596-604`）推算何時會超過門檻值（Speed Loss % 或油耗超額成本），這是全新邏輯。
- 需要同時修正 `MaintenanceCorrelation.vue` 用假公式畫油耗的問題，改接真實資料，這會動到既有頁面的行為。

### 後端
- 新端點：`GET /api/v1/vessels/{vessel_id}/health-trend`
  - 依 `NOON_UTC` 排序整理每日：`day`、`speed_loss_pct`（沿用 speed-loss 端點已有的 slip 計算）、`me_consumption_mt`（真實 `ME_CONSUMPTION`，不再用假公式）
  - 依 `maintenance-events` 的 `event_day` 切成多個區段（對應白板圖的 3 個面板）
  - 每個區段分別做線性回歸，算出成長率
  - 套用門檻（先給預設值，如 Speed Loss > 8% 或對照 `get_maintenance_recommendation` 的 `URGENT` 邏輯 slip > 10%）外推出「預估觸發門檻的日期」，作為「建議進塢時間點」回傳
  - 檔案：`backend-api/handler.py`（新函式 + `route()` dispatch table 註冊 `handler.py:218-268`）
- 需要決定門檻是寫死常數，還是做成可設定參數（建議先寫死，MVP 夠用，Task 5 的 ROI 卡片可以重用同一個門檻）

### 前端
- 新元件（建議獨立，方便重用）：`frontend/src/components/vessel/VesselHealthTrendChart.vue`
  - `vue-echarts` 雙 Y 軸折線圖：左軸 Speed Loss %、右軸油耗 MT/日
  - 維修事件用 `markLine`（垂直虛線，重用 `SpeedLoss.vue:229-296` 已有的做法）
  - 「建議進塢時間點」用 `markArea` 或醒目的 `markPoint` + tooltip 文字提示
- 放置位置：升格成 `VesselOverview.vue` 最上方的主視覺（取代目前分散的 Speed Loss / 油耗兩張獨立 KPI 卡，`VesselOverview.vue:140-185`），而不是繼續埋在 `MaintenanceCorrelation.vue` 裡
- 同步修正 `MaintenanceCorrelation.vue` 的時間軸圖，改呼叫新端點拿真實油耗，移除假公式（`MaintenanceCorrelation.vue:22,50,219`）
- 新增 API type + fetcher：`frontend/src/api/client.ts`、`frontend/src/api/adapter.ts`

**預估：後端 3–4 hr（新的回歸+外推邏輯較花時間），前端 3–5 hr（新圖表元件 + 改版 VesselOverview + 修正舊頁面）**

---

## Task 2：岸上管理員 — 提交養護工單申請

**對應需求 1。** 目前後端完全沒有寫入路徑，這是第一個 `POST` 端點，記得檢查 Lambda 執行角色是否有 DynamoDB `PutItem` 權限（目前 IAM role 大概只設定了 `Query`/`GetItem`）。

**⚠️ 範圍澄清**：專案目前沒有登入/角色系統，「岸上管理員」跟其他任何打開網站的人是同一個身分。這個 MVP 不做權限驗證，任何人都能送出申請——如果之後要限制，需要另外規劃登入機制（不在本次任務範圍）。

### 後端
- 新 DynamoDB table，例如 `ship-analysis-dev-maintenance-requests`：`vessel_id`、`request_id`（uuid）、`requested_at`、`status`（初始 `已申請養護`）、`note`（申請原因，選填）
- 新端點：`POST /api/v1/vessels/{vessel_id}/maintenance-requests`，body 含 `note`，寫入後回傳建立的 request
- 檔案：`backend-api/handler.py`（新函式 + route），環境變數/Terraform 或 `serverless.yml` 需加這張新表與 IAM 權限

### 前端
- `VesselOverview.vue`（及可選：`VesselList.vue` 列表上的快速按鈕）加「申請養護」按鈕，點擊開 Modal 填寫原因，送出後呼叫新 API
- 送出成功後即時把狀態徽章更新為「已申請養護」（樂觀更新或重新 fetch）

**預估：後端 2 hr（含 IAM 權限設定的除錯時間），前端 1.5–2 hr**

---

## Task 3：養護狀態顯示與推進（未申請養護 / 已申請養護 / 已通過 / 養護中）

**對應需求 2。** 建立在 Task 2 的表之上。因為沒有審核角色，這個 MVP 用「手動推進」取代真正的簽核流程——在畫面上放一個狀態切換控制，讓操作者自己把狀態往前推。

### 後端
- 擴充 Task 2 的 table，`status` 允許 `未申請養護 | 已申請養護 | 已通過 | 養護中`
- 新端點：`PATCH /api/v1/vessels/{vessel_id}/maintenance-requests/{request_id}`，body 帶 `status`，做狀態推進
  - 當狀態進到「養護中」完成、要收尾時，可選擇順手寫一筆進 `maintenance-events` 表（銜接既有的維修事件時間軸），但這屬於加分，非必須
- 新端點：`GET /api/v1/vessels/{vessel_id}/maintenance-requests`（取最新一筆，供列表/總覽頁顯示狀態徽章用）；也可以直接把最新狀態併進既有的 `GET /api/v1/fleet/summary`，減少前端多打一次 API

### 前端
- 新共用元件：`MaintenanceStatusBadge.vue`，4 態各自配色（沿用現有 urgency 配色風格）
- 套用到 `FleetOverview.vue`、`VesselList.vue`、`VesselOverview.vue`（取代目前只顯示 urgency、且從未被渲染的 `maintenanceStatus`）
- 狀態旁加簡單的「推進」按鈕/下拉（例如「標記為已通過」「開始養護」）

**預估：後端 2 hr，前端 2–2.5 hr**

---

## Task 4：每日 Noon Report 填報 + 即時閥值檢查

**對應需求 4。** 目前 Noon Report 是唯讀表格，資料來自比賽提供的靜態 CSV。這個任務要開一個「新增今日資料」的入口，並在送出後立刻套用 Task 1 算出的門檻邏輯。

### 後端
- 新端點：`POST /api/v1/vessels/{vessel_id}/noon-reports`
  - Body 對照現有 schema（`AVG_SPEED`、`SPEED_THROUGH_WATER`、`ME_AVG_RPM`、`FORE_DRAFT`/`AFTER_DRAFT`、`WIND_SCALE`、`SEA_HEIGHT`、`ME_CONSUMPTION` 等，完整欄位列表見 `backend/hackathon-data/README.md:37-91`），做基本型別/範圍驗證
  - 寫入 `ship-analysis-dev-vessel-data` 表（新的一天）
  - 寫入後立刻重用 Task 1 的門檻判斷函式，回應中附上 `threshold_triggered: boolean` 及觸發的是 Speed Loss 還是油耗
- 檔案：`backend-api/handler.py`

### 前端
- `NoonReports.vue` 加「+ 新增今日 Noon Report」按鈕/表單（欄位對照 schema，帶合理預設值與基本驗證）
- 送出後：
  - 成功則刷新表格
  - 若 API 回傳 `threshold_triggered`，顯示醒目提醒 banner（例如「本日 Speed Loss 已超過門檻，建議申請養護」），banner 上放 CTA 按鈕直接開啟 Task 2 的「申請養護」Modal，形成完整的操作閉環

**預估：後端 3 hr（驗證 + 寫入 + 重用門檻邏輯），前端 2.5–3 hr（表單 + 提醒 banner + 串接申請 CTA）**

---

## Task 5（加碼建議）：節能效益 / ROI 卡片

這不是你列的 4 點之一，但直接對應你說的「油耗可以換算 ROI」這個核心價值主張，而且後端邏輯已經有一半現成的，補完的成本很低，建議一起做。

### 現況
`get_maintenance_recommendation`（`backend-api/handler.py:581-657`）已經算出：目前平均油耗、Speed Loss 成長率、`FUEL_PRICE = 620 USD/MT`，以及「延後養護 N 天」的累積超額油耗成本曲線。`MaintenanceCorrelation.vue` 也已經把這條曲線畫成圖（COR-01 面板）。缺的是：這條曲線沒有跟 Task 1 算出的「建議進塢時間點」串起來，也沒有直接換算成一句人話：「現在養護可省下 $X」。

### 後端
- 小幅擴充 `get_maintenance_recommendation`：接受 Task 1 算出的建議進塢日期（或直接在同一次呼叫裡重算），回傳「現在養護」vs「拖到門檻觸發那天才養護」兩者的累積成本差額，作為 `estimated_saving_usd`

### 前端
- 在 Task 1 的健康趨勢圖旁加一張小卡片：「預估節省油耗 X MT／換算 $Y USD／建議在 Z 天內處理」
- 可直接放在 `VesselOverview.vue`，緊貼著 Task 1 的主視覺圖

**預估：後端 1.5–2 hr，前端 1–1.5 hr**

---

## 建議施工順序

1. **Task 1** 先做，把「整合呈現」的資料與門檻邏輯打好地基。
2. **Task 2 → Task 3** 一起做（同一張表，狀態機接續），做完就有完整的「申請 → 通過 → 養護中」可展示。
3. **Task 4** 接上 Task 1 的門檻判斷，做完就有「填報 → 即時預警 → 一鍵申請養護」的完整故事線。
4. **Task 5** 最後補，把整套系統的 ROI 講清楚，適合放在 demo 結尾當總結亮點。
