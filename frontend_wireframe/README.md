# Fleet Ops Dashboard — Wireframe

低擬真線框稿（wireframe），用於黑客松期間的團隊內部討論，刻意不使用最終視覺設計（品牌色、字體、特效、圖片）。純 HTML/CSS/JS 靜態頁面，不需安裝任何套件，直接用瀏覽器打開即可。

## 如何瀏覽

直接在瀏覽器打開 `index.html`（或用 VS Code 的 Live Server / `python3 -m http.server` 起一個靜態伺服器），透過頂部導覽列在頁面間切換。

```bash
cd frontend_wireframe
python3 -m http.server 8080
# 開啟 http://localhost:8080
```

## 頁面對照（對應原 `frontend/` 路由）

| Wireframe 檔案 | 對應原路由 | 說明 |
|---|---|---|
| `index.html` | `/` (FleetOverview) | 船隊總覽：KPI、地圖、優先處理排行 |
| `vessels.html` | `/vessels` (VesselList) | 船隊列表：篩選、排序表格、展開污損量表 |
| `vessel-detail.html` | `/vessels/:imo/*` (VesselLayout + 6 個子頁) | 單船詳情，以分頁（tabs）方式呈現六個子頁：總覽 / Noon Report / 水下檢查 / Speed Loss / 油耗歸因 / 維修建議 |
| `fleet-analytics.html` | `/fleet-analytics` (FleetAnalytics) | 跨船隊分析：疊圖比較、排行表 |

語音對話模式（design_docs/3）以右上角圖示按鈕觸發全螢幕 overlay 佔位，非文件內另開頁面。

## 設計原則

- 全灰階、虛線框、斜紋填色區塊代表地圖/圖表/照片等尚未定案的視覺元件
- 版面結構（欄位排列、卡片分區、資訊層級）盡量對齊現有實作，方便對照討論
- 不含任何品牌色、logo 圖像、字體特效
- 可點擊、可展開/收合、可切換分頁，模擬基本互動，但不含真實資料或 API

## 目錄結構

```
frontend_wireframe/
├── index.html              船隊總覽
├── vessels.html             船隊列表
├── vessel-detail.html       單船詳情（六個分頁）
├── fleet-analytics.html     跨船隊分析
├── assets/
│   ├── wireframe.css        共用線框稿樣式
│   └── wireframe.js         共用互動腳本（tabs / accordion / nav toggle 等）
└── README.md
```
