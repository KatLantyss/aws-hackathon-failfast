# 船隊維運 Dashboard — Frontend Design Requirements

> 給 Kiro / Claude Code 的前端開發需求文件
> 版本：v1.0　最後更新：2026-07-09

---

## 1. 專案概述

### 1.1 目標
打造一個貨船公司內部使用的船隊維運分析平台，讓船隊技術部門（Fleet Technical Superintendent、船隊經理）能夠：

1. 一覽全船隊船況與位置
2. 檢視每艘船的 Noon Report 歷史數據
3. 檢視水下檢查報告（含污損分級、照片）
4. 互動式檢視 Speed Loss 隨時間變化趨勢
5. 理解油耗預測模型的歸因結果（船體 / 螺旋槳 / 天氣 / 主機老化各佔多少）
6. 取得「最佳維修時機」建議（含成本效益依據）

### 1.2 核心使用者
| 角色 | 需求 |
|---|---|
| Fleet Technical Superintendent | 逐船判斷是否該安排坐塢、水下清洗、螺旋槳打磨 |
| Fleet Manager / 高層 | 跨船隊比較、預算規劃、KPI 總覽 |
| 船舶操作 / Charterer 對接人員 | 查詢速度/油耗保證條款相關數據佐證 |

### 1.3 本文件範圍
僅涵蓋**前端呈現與互動需求**。資料模型、演算法細節請參考另一份《資料與模型架構文件》，此處僅定義前端需要消費的資料形狀（見第 6 節）。

---

## 2. 資訊架構（Site Map）

```
/                          → 船隊總覽 Dashboard (Fleet Overview)
/vessels                  → 船隊列表（表格 + 篩選）
/vessels/:imo             → 單船詳情頁
  ├─ /overview            → 基本資料 + 目前位置 + 關鍵指標卡
  ├─ /noon-reports         → Noon Report 歷史表格 + 異常標記
  ├─ /inspections          → 水下檢查報告列表 + 檢視器
  ├─ /speed-loss           → Speed Loss 互動分析（核心頁）
  ├─ /fuel-attribution      → 油耗歸因儀表板（SHAP 視覺化）
  └─ /maintenance-advisor  → 維修時機建議 + 成本效益模擬
/fleet-analytics           → 跨船隊比較 / 排名 / KPI
```

---

## 3. 視覺設計方向（Design Direction）

**明確要求：不要走「暖白底 + 陶土色」「近黑底 + 螢光綠」「報紙式細線」這三種常見 AI 生成樣板。這是一個航運業的專業數據工具，視覺語言應該向航海圖 (nautical chart) 與船舶儀表取材。**

### 3.1 設計主題：「航海圖 × 船舶儀表」
以海圖的等深線、方位刻度、聲測儀 (fathometer) 讀數作為視覺語言基礎，讓資料密集的介面帶有航運業的專業質感，而不是通用 SaaS 樣板。

### 3.2 色彩系統（Design Tokens）

| Token 名稱 | Hex | 用途 |
|---|---|---|
| `--marine-navy` | `#0B1F33` | 主背景（深色模式基底）、頂部導航 |
| `--chart-paper` | `#EDE6D6` | 卡片/面板底色（模擬海圖紙），數據表格背景 |
| `--brass-amber` | `#C08A3E` | 主要強調色：CTA、選中狀態、警示（中度） |
| `--signal-red` | `#C1443C` | 嚴重警示：污損嚴重、需立即維修 |
| `--fathom-teal` | `#3E7C74` | 正常/健康狀態、正向趨勢 |
| `--ink-slate` | `#28313C` | 正文文字、圖表軸線 |

> 全站採**淺色海圖紙為主要工作區底色**（`--chart-paper`），深色 `--marine-navy` 僅用於頂部導航列與側邊欄，形成「儀表艙 + 海圖桌」的對比感，避免整頁死板深色。

### 3.3 字體系統

| 角色 | 字體建議 | 用途 |
|---|---|---|
| Display（標題） | `Oswald` 或 `Bebas Neue`（窄體、大寫、間距加寬） | 頁面標題、船名、KPI 大數字，模擬船舷編號/註冊牌 |
| Body（正文） | `IBM Plex Sans` 或 `Inter` | 說明文字、表格內文、UI 標籤 |
| Data/Mono（數據） | `IBM Plex Mono` | 所有數值型讀數（速度、油耗、座標、時間戳），模擬 AIS/GPS 儀表讀數的等寬對齊感 |

**規則**：任何純數字型的資料（速度、噸位、座標、百分比）一律使用 Mono 字體並右對齊，讓表格與圖表的數字有「儀表讀數」的專業感。

### 3.4 版面語言
- 面板之間使用 **極細的海圖等深線風格分隔線**（1px，`--ink-slate` 20% opacity），而非陰影卡片
- 每個資料面板左上角加**座標式標籤**（例如 `SPD-01`、`FUEL-A2`），模擬海圖圖例編號，用於區塊識別而非裝飾
- 圓角統一為 **2px**（近乎直角），呼應儀表面板/海圖圖例的工業感，不使用大圓角

### 3.5 Signature 元素：「測深計式」污損/風險量表
全站最具識別性的元件：用**垂直測深計 (fathometer) 造型**呈現「船體污損程度」「距下次維修建議天數」等單一數值型風險指標——一條垂直刻度尺，指針位置代表當前數值，刻度上標示「Clean / Light / Moderate / Heavy」分級與對應的維修建議顏色區帶。此元件在船隊列表、單船總覽、維修建議頁重複出現，成為全站的識別符號。

### 3.6 動態效果
- 進場動畫：Speed Loss 圖表載入時，趨勢線以「掃描筆」效果從左至右繪出（模擬聲測儀掃描），僅此一處使用強調動畫
- 其餘互動（hover、篩選）皆為 150ms 內的淡入淡出，不使用彈跳/縮放等花俏效果
- 尊重 `prefers-reduced-motion`

---

## 4. 頁面級需求

### 4.1 船隊總覽 Dashboard（`/`）
- 頂部 KPI 卡片列：船隊總數、目前航行中、目前停靠港、待安排維修船數、本月累積超額油耗成本
- 主視覺：船隊地圖（技術規格見 4.1.1），標記各船目前位置與航向，點擊船圖示彈出迷你資訊卡（船名、航速、下個檢查建議日）
- 右側：「需優先處理」船隻排行榜（依維修建議急迫度排序，使用測深計 signature 元件顯示風險值）

#### 4.1.1 地圖元件規格（功能性參考 VesselFinder，視覺不抄）

> 說明：本產品的地圖情境是「單一船隊、十幾到幾十艘船」，資料量級遠低於 VesselFinder（全球數萬艘船即時追蹤），因此不需要它那套大規模效能架構（WebGL 大量渲染、supercluster 分群演算法等），但可以直接借用它「好用的互動細節」。以下為具體驗收規格，取代模糊的「做得跟 VesselFinder 一樣好」：

**借用的互動模式（功能性參考，非視覺抄襲）**
- 船舶圖示為三角形/箭頭 SVG，依 AIS 航向 (heading) 即時旋轉，而非固定圖釘
- 點擊船舶圖示彈出迷你資訊卡的互動節奏（單擊彈出、再次點擊或點空白處關閉）
- 船隻列表頁的篩選欄位排列邏輯（船型、狀態、關鍵字並排於表格上方）

**技術驗收標準**
| 項目 | 標準 |
|---|---|
| 底圖圖層 | OpenSeaMap 海事圖層（非一般街景圖），呼應第 3 節「航海圖」視覺方向 |
| 圖示旋轉 | SVG 三角形圖示依 heading 即時旋轉 |
| 位置更新動畫 | 新座標到達時以 300–500ms 平滑位移過渡，不可瞬間跳格 |
| 縮放/拖曳效能 | 需維持 60fps（可用 Chrome DevTools Performance 面板量測驗收） |
| 點擊回應延遲 | 點擊船舶圖示至資訊卡彈出 < 100ms（資料須預載於前端，不即時打 API） |
| 重疊處理 | 同港口多船停靠位置重疊時，需錯位顯示或群聚提示，避免圖示互相遮蓋 |

**驗收方式建議**：開發完成後，將本產品地圖與 VesselFinder 並排做同樣操作（拖曳、縮放、點擊船舶），比對縮放流暢度、圖示旋轉/移動自然度、底圖質感三項，作為主觀驗收輔助。

### 4.2 船隊列表（`/vessels`）
- 表格欄位：船名、IMO、船型、船齡、目前 Speed Loss %、上次坐塢日、下次建議維修窗口、狀態燈（綠/黃/紅）
- 支援：欄位排序、船型篩選、狀態篩選、關鍵字搜尋
- 每列可展開顯示測深計風險量表縮圖

### 4.3 單船總覽（`/vessels/:imo/overview`）
- 船舶基本資料卡（船型、噸位、主機型號、建造年）
- 目前位置 + 最近 10 個港口停靠時間軸
- 3 個關鍵指標卡：目前 Speed Loss %、距上次水下清洗天數、本季累積超額油耗成本
- 快速連結至 Noon Report / 檢查報告 / Speed Loss / 油耗歸因 / 維修建議

### 4.4 Noon Report 歷史（`/vessels/:imo/noon-reports`）
- 表格呈現：日期、位置、航速(觀測)、航速(修正後)、油耗、海況(Beaufort)、吃水、Ballast/Laden 狀態
- 異常值（清洗異常偵測標記）以 `--signal-red` 底色標示該列，hover 顯示判定原因（例如「油耗較同海況基準高 22%」）
- 支援日期區間篩選、CSV 匯出

### 4.5 水下檢查報告（`/vessels/:imo/inspections`）
- 時間軸列表：每次檢查的日期、檢查單位、整體污損分級（Clean/Light/Moderate/Heavy，用測深計量表呈現）
- 點擊展開：檢查照片/影片縮圖網格、船體分區污損標示（可用簡化船體俯視圖，依區塊上色標示污損程度）
- 檢查報告 PDF 原文可下載

### 4.6 Speed Loss 互動分析（`/vessels/:imo/speed-loss`）— **核心頁面**

這是整個產品的核心互動頁面，需求最細，請特別注意。

**主圖表**
- 橫軸：時間（可切換為「距上次清洗天數」）
- 縱軸：修正後 Speed Loss（%），相對於乾淨船體基準曲線
- 資料點：每個 Noon Report 為一個散點，依 Ballast/Laden 狀態用不同符號區分
- 疊加線：
  - 乾淨船體基準線（水平參考線，來自 Sea Trial）
  - 污損趨勢擬合曲線（迴歸線，展示污損隨時間增長速率）
- 事件標記：垂直虛線標出坐塢日、水下清洗日、螺旋槳打磨日（hover 顯示事件詳情）

**互動控制項**
- 日期區間拖曳滑桿
- 海況篩選開關：「僅顯示 Beaufort ≤ 3」（排除天氣干擾以看清污損趨勢）
- Ballast / Laden 切換顯示
- 「比較上次清洗週期」按鈕：並排顯示前一個清洗週期的趨勢曲線做對比

**輔助面板（圖表右側或下方）**
- 所選區間統計卡：平均 Speed Loss、估算超額油耗成本、污損增長速率（%/月）
- 「建議下次清洗窗口」提示卡，附一句話理由（例如「污損增長速率高於船隊平均，建議提前 3 週安排」）

### 4.7 油耗歸因儀表板（`/vessels/:imo/fuel-attribution`）

- **主視覺**：Waterfall Chart（瀑布圖），展示單一航次或所選期間的「油耗差異拆解」：
  基準油耗 → + 天氣影響 → + 船體污損影響 → + 螺旋槳污損影響 → + 主機老化影響 → = 實際油耗
  每個影響因子用不同顏色區塊表示正/負貢獻
- **輔助圖**：SHAP Summary Plot 風格的橫向條圖，展示所有航次匯總後各特徵的平均影響程度排序
- **時間序列版本**：可切換為堆疊面積圖，展示各歸因因子的影響隨時間變化（用於觀察「船體污損佔比是否持續上升」）
- 每個歸因區塊 hover 顯示白話解釋文字（非統計術語），例如：「本趟因船體污損多燒了 1.8 噸燃油，約占超額油耗的 61%」

### 4.8 維修時機建議（`/vessels/:imo/maintenance-advisor`）

- 主要呈現：**成本效益模擬曲線** — 橫軸為「延後維修天數」，縱軸疊加兩條線：累積超額油耗成本（隨延後天數增加）vs. 維修/停租機會成本（隨提前執行增加），交叉點即為建議時機
- 建議卡：明確標示建議執行維修的日期區間、預期節省金額、信心程度（依可用資料量標示 高/中/低）
- 「未盡之處」提示區：若該船資料量不足（例如檢查次數過少），需明確告知使用者此建議的資料侃限，避免誤導決策

### 4.9 跨船隊分析（`/fleet-analytics`）
- 同型船污損曲線疊圖比較，用於找出異常船隻
- 船隊排名表：依 Speed Loss、超額油耗成本、維修急迫度排序
- 匯出月報 PDF 功能

---

## 5. 互動與體驗要求

- **所有數據圖表必須支援 hover tooltip**，且 tooltip 內容為白話文字，不只是原始數值
- **所有頁面須支援 Loading / Empty / Error 三態**，Empty 狀態需明確引導下一步（例如「此船尚無水下檢查記錄，前往新增」），語氣為介面語氣而非道歉語氣
- **響應式**：主要使用場景為桌機/平板（船隊辦公室環境），手機版僅需支援船隊總覽與單船總覽的簡化瀏覽，Speed Loss 與歸因圖表可標示「建議於桌面檢視」
- **可及性**：所有互動元件需有可見的鍵盤 focus 樣式，色彩警示（紅/黃/綠）需搭配圖示或文字標籤，不可僅依賴顏色傳達資訊（色盲友善）
- **效能**：單船 Speed Loss 圖表若資料點超過 500 筆，需做取樣或分頁渲染，避免卡頓

---

## 6. 前端所需資料形狀（供 Kiro 對接 Mock/API 使用）

以下為前端元件預期消費的資料格式範例，實際欄位以後端 API 文件為準，此處供前端先行以 mock data 開發。

```json
// GET /api/vessels/:imo/speed-loss
{
  "vessel": { "imo": "1234567", "name": "MV EXAMPLE", "type": "Bulk Carrier" },
  "cleanBaseline": { "speedKnots": 14.2, "source": "sea_trial_2023" },
  "events": [
    { "date": "2025-03-10", "type": "hull_cleaning" },
    { "date": "2025-09-02", "type": "propeller_polishing" }
  ],
  "reports": [
    {
      "date": "2025-01-15",
      "observedSpeed": 13.1,
      "correctedSpeed": 13.6,
      "speedLossPct": 4.2,
      "loadCondition": "laden",
      "beaufort": 3,
      "fuelConsumptionMt": 28.4,
      "isAnomaly": false
    }
  ]
}

// GET /api/vessels/:imo/fuel-attribution?voyageId=V123
{
  "baselineFuelMt": 26.0,
  "actualFuelMt": 30.1,
  "attribution": [
    { "factor": "weather", "impactMt": 0.6, "label": "天氣（風浪）" },
    { "factor": "hull_fouling", "impactMt": 2.5, "label": "船體污損" },
    { "factor": "propeller_fouling", "impactMt": 0.7, "label": "螺旋槳污損" },
    { "factor": "engine_degradation", "impactMt": 0.3, "label": "主機老化" }
  ],
  "confidence": "medium"
}

// GET /api/vessels/:imo/maintenance-advisor
{
  "recommendation": {
    "action": "hull_cleaning",
    "windowStart": "2026-08-01",
    "windowEnd": "2026-08-15",
    "estimatedSavingUsd": 42000,
    "confidence": "high",
    "reasoning": "船體污損增長速率高於船隊平均 1.4 倍"
  },
  "dataLimitations": [
    "本船僅有 2 次水下檢查記錄，趨勢估計信心中等"
  ]
}
```

---

## 7. 建議技術棧

| 項目 | 建議 |
|---|---|
| 框架 | Vue 3（Composition API）+ TypeScript |
| 樣式 | Tailwind CSS（依第 3 節 tokens 客製 theme） |
| 圖表 | vue-chartjs 或 vue-echarts（一般圖表）+ D3（Waterfall / 測深計 signature 元件需自製 SVG） |
| 地圖 | MapLibre GL JS（向量圖磚渲染，體感較 Leaflet 流暢，接近 VesselFinder 的縮放/渲染質感；船隻數量少，效能綽綽有餘）+ OpenSeaMap 海事圖層 |
| 表格 | TanStack Table（Vue adapter，排序/篩選/虛擬化） |
| 狀態管理 | Pinia（全域狀態）+ TanStack Query（Vue Query，資料抓取/快取） |
| PDF 檢視 | vue-pdf 或直接使用 pdf.js（水下檢查報告原文） |

---

## 8. 開發優先順序建議（供 Kiro 分階段開發）

1. **Phase 1**：船隊列表 + 單船總覽（先用 mock data 跑通資訊架構與 design tokens）
2. **Phase 2**：Speed Loss 互動頁（核心頁面，含測深計 signature 元件）
3. **Phase 3**：油耗歸因儀表板（Waterfall + SHAP 條圖）
4. **Phase 4**：Noon Report / 水下檢查報告瀏覽頁
5. **Phase 5**：維修時機建議 + 跨船隊分析

---

## 9. 驗收檢查清單

- [ ] 色彩、字體、圓角、分隔線皆遵循第 3 節 design tokens，未混用預設 Tailwind 灰階
- [ ] 測深計 signature 元件在至少 3 個頁面一致出現
- [ ] 所有數值資料使用 Mono 字體並右對齊
- [ ] Speed Loss 頁面互動控制項（日期滑桿、海況篩選、Ballast/Laden 切換）皆可運作
- [ ] 所有圖表 hover tooltip 為白話文字，非原始 JSON
- [ ] Loading / Empty / Error 三態皆有設計
- [ ] 鍵盤可完整操作，focus 樣式清晰可見
- [ ] 手機版至少船隊總覽與單船總覽可正常瀏覽
- [ ] 地圖符合 4.1.1 節技術驗收標準（船舶圖示旋轉、平滑位移動畫、60fps 縮放、<100ms 點擊回應、重疊錯位處理）
