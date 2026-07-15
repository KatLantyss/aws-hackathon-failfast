# Design Tasks — 2 小時快速落地版

> 完整版見 [`Design_Tasks.md`](./Design_Tasks.md)。這份是時間只剩 2 小時時的砍法：**跳過所有新的後端統計/回歸邏輯，只做一個必要的寫入端點**，其餘用前端合併現有 API 撐出同樣的敘事效果。

## 砍的原則

1. 完整版 Task 1（船舶健康趨勢圖）估 6–9hr，貴在「油耗趨勢回歸」「進塢時間點外推演算法」這兩個全新後端邏輯。2 小時內不寫這兩個，改用**前端合併既有 3 個 GET API + 簡單線性外推**頂替，效果一樣、零後端風險。
2. 完整版 Task 2+3（申請＋4 態狀態機）本來是 2 個端點（POST 建立、PATCH 推進）。2 小時內合併成**1 個 upsert 端點**，用同一支 API 處理建立與狀態推進。
3. 完整版 Task 4（Noon Report 填報＋即時閥值）、Task 5（ROI 卡片）**整個跳過**，時間不夠做到能展示的完整度。

---

## 任務總覽

| # | 任務 | 對應完整版 | 動後端？ | 預估 |
|---|---|---|---|---|
| 1 | 健康趨勢圖（前端合併版） | Task 1 精簡 | ❌ 不動 | ~50 分 |
| 2 | 申請養護＋4 態狀態切換（單端點版） | Task 2+3 合併精簡 | ✅ 新增 1 個 upsert 端點 | ~40–50 分 |

**合計 90–100 分，留 20–30 分緩衝做測試/demo 排練。**

---

## Task 1：健康趨勢圖（前端合併，不碰後端）

**目標**：一張圖同時呈現 Speed Loss、真實油耗、維修事件、建議進塢時間點——對應原始需求 0 + 3。

**做法（全部在前端，零後端改動）**：
- 資料來源，三支既有 GET API 直接重用：
  - `GET /api/v1/vessels/{id}/speed-loss` → 每日 Speed Loss（slip）序列
  - `GET /api/v1/vessels/{id}/noon-reports` → 每日真實 `ME_CONSUMPTION`（油耗）
  - `GET /api/v1/vessels/{id}/maintenance-events` → 維修事件日期（畫垂直線）
  - `GET /api/v1/vessels/{id}/maintenance-recommendation` → 已經算好的 `avg_slip`、`degradation_rate_pct_per_day`（拿來做簡單線性外推，不用重新設計演算法）
- 前端把 speed-loss 與 noon-reports 兩組資料依 `day`/`NOON_UTC` 對齊 zip 成一組陣列
- 建議進塢時間點：`預估天數 = (門檻值 - avg_slip) / degradation_rate_pct_per_day`（門檻值先寫死，例如 10%），畫成 `markLine`/`markArea` 標在圖上，文字寫「預估約 N 天後建議進塢養護」
- 新元件：`frontend/src/components/vessel/VesselHealthTrendChart.vue`（`vue-echarts` 雙 Y 軸折線圖，維修事件 `markLine` 參考 `SpeedLoss.vue:229-296` 現成寫法）
- 塞進 `VesselOverview.vue` 最上方，取代目前分散的 Speed Loss / 油耗兩張獨立 KPI 卡（`VesselOverview.vue:140-185`）

**不做**：`MaintenanceCorrelation.vue` 假油耗公式先不修（不影響新頁面，之後有時間再補）；不做可設定門檻，門檻先寫死常數。

---

## Task 2：申請養護＋4 態狀態切換（單端點）

**目標**：岸上人員可以按按鈕送出申請，畫面上看得到並能推進「未申請養護／已申請養護／已通過／養護中」——對應原始需求 1 + 2。

**⚠️ 唯一會動到後端寫入的地方**，記得先確認 Lambda 執行角色有 DynamoDB `PutItem` 權限（目前全專案沒有任何寫入 API，這是第一個）。

**做法**：
- 新一張 DynamoDB table：`ship-analysis-dev-maintenance-requests`（key：`vessel_id`），只存最新一筆狀態，不做歷史記錄
- 新**一個** upsert 端點：`PUT /api/v1/vessels/{vessel_id}/maintenance-request`，body 帶 `{ status }`，直接覆寫該船的狀態（不分建立/推進兩支 API，省掉 request_id 設計）
  - 檔案：`backend-api/handler.py`（新函式 + `route()` 註冊）
- 新一個讀取端點（或直接塞進既有 `GET /api/v1/fleet/summary` 回應裡，省一次前端 fetch）：回傳目前狀態，預設 `未申請養護`
- 前端：
  - `VesselOverview.vue` 加一顆「申請養護」按鈕（直接 PUT `已申請養護`，不做填寫原因的 Modal）
  - 旁邊放狀態徽章（4 色）＋一顆「推進狀態」按鈕，依序 `已申請養護 → 已通過 → 養護中`

**不做**：不留申請原因/備註欄位、不做審核角色區分、不寫回 `maintenance-events` 歷史表、不做 `VesselList.vue`/`FleetOverview.vue` 上的徽章同步（只在單船頁面做，時間不夠就先聚焦一個畫面）。

---

## 時間分配建議（2 小時 = 120 分）

| 時段 | 內容 |
|---|---|
| 0–50 分 | Task 1：健康趨勢圖元件 + 塞進 VesselOverview |
| 50–100 分 | Task 2：新端點 + IAM 權限確認 + 按鈕/徽章 |
| 100–120 分 | 過一次完整流程（開頁面看圖、按申請按鈕、推進狀態），修明顯的 bug，準備 demo 講稿 |

## Demo 講稿要點

1. 打開船舶總覽頁 → 指著新的健康趨勢圖：「這是這艘船的 Speed Loss 跟真實油耗，兩者一起漲，系統算出大概還有 N 天就該進塢養護」
2. 按下「申請養護」→ 狀態徽章變成「已申請養護」→ 再按一次推進到「已通過」「養護中」：「岸上人員從這裡直接送出申請並追蹤進度」
3. 收尾一句：「這是 2 小時內的 MVP，後端真正的回歸演算法、Noon Report 每日填報、ROI 換算卡片是下一步（見完整版 Design_Tasks.md）」
