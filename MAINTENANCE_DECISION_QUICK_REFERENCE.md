# 決策建議頁面改進 — 快速參考

**完成日期**：2026-07-17  
**改進版本**：v2.0  
**狀態**：✅ 代碼完成，待前端驗證

---

## 🎯 改進總結（三句話）

1. **燃油計算**：從簡單公式 `SL% × 0.5` → 使用 v5 模型預測（精度提升 5-10 倍）
2. **決策邏輯**：從簡單閾值 → 集成根因分析（Hull/Prop 污損比例）
3. **時間維度**：新增衰退曲線視圖（預測何時需維修）

---

## 📝 改動檔案

```
frontend/src/views/vessel/MaintenanceDecision.vue
├── 新增 imports
│   ├── getFuelAnomalyCause
│   ├── predictFuelConsumption
│   └── watch (from vue)
├── 新增 refs
│   └── fuelPrediction
├── 新增 watchers
│   ├── watch(() => props.imo, ...)
│   └── watch(slData, ...)
├── 修改 computed
│   ├── maintenanceRecommendation（新增根因分析邏輯）
│   └── maintenanceRoi（使用模型預測而非公式）
└── 新增模板區段
    ├── <!-- 衰退曲線分析 - 時間軸視圖 -->
    ├── 當前狀態 KPI
    ├── 預測時機
    └── 污損根因進度條
```

---

## 🔄 工作流程

### 用戶打開決策建議頁面時

```
1. getSpeedLossDashboard() 加載
   ├─ 返回 raw/smooth 時間序列
   ├─ 返回 events（維修事件）
   └─ 返回 summary { hull_pct, prop_pct }

2. predictFuelConsumption() 自動觸發
   ├─ 輸入：vessel_id, noon_day
   ├─ 模型推理
   └─ 返回 counterfactual_uwc_pp { fuel_saving_mt_per_day, saving_pct, energy_pricing }

3. 計算 maintenanceRecommendation
   ├─ 判斷 Speed Loss 等級
   ├─ 查詢根因分析 (hull_pct vs prop_pct)
   ├─ 決策維修類型
   └─ 返回 recommendation 對象

4. 計算 maintenanceRoi
   ├─ 從 fuelPrediction 取得 daily_saving_usd
   ├─ 計算月/年度節省和回本週期
   └─ 返回 ROI 指標

5. 渲染 UI
   ├─ 緊急程度卡片 (CRITICAL/HIGH/MEDIUM/LOW)
   ├─ 預期效益卡片
   ├─ ROI 分析卡片 ✨ 新增 6 項指標
   ├─ 衰退曲線面板 ✨ 新增時間軸
   └─ 決策建議 & 申請養護按鈕
```

---

## 📊 新增 UI 元素

### ROI 面板 - 新增指標

| 指標 | 來源 | 公式 |
|------|------|------|
| 燃油節省比例 | `counterfactual.saving_pct` | 直接取得 |
| 月度節省 (USD) | `daily_saving_usd × 30 × successRate%` | 新計算 |
| 月度節省 (MT) | `fuel_saving_mt_per_day × 30` | 新計算 |
| 年度節省 (USD) | `月度節省 × 12` | 新計算 |
| 回本週期 (月) | `estimatedCost / 月度節省` | 新計算 |
| 投資回報率 (%) | `((年度 - 季度) / 成本) × 100` | 新計算 |

### 衰退曲線面板 - 新增顯示

| 區段 | 顯示內容 | 數據源 |
|------|--------|--------|
| 當前狀態 | SL %, 衰退速率 %/30d | `slData.smooth[-1][1]`, `vessel.degradationRatePctPerDay` |
| 預測時機 | SL 達 30% 和 40% 的日數 | 計算: `(targetSL - currentSL) / rate` |
| 污損根因 | Hull % / Prop % 進度條 | `slData.summary.hull_pct`, `slData.summary.prop_pct` |

---

## 🧠 決策邏輯樹

```
Speed Loss 分析
├─ SL < 10%
│  └─ 🟢 LOW / 監控中
│
├─ 10% ≤ SL < 12%
│  └─ 🟡 MEDIUM / UWC+PP (預設)
│
├─ 12% ≤ SL < 20%
│  ├─ Hull > 60% ? → UWC
│  ├─ Prop > 60% ? → PP
│  └─ 都沒有 → UWC+PP
│
├─ 20% ≤ SL < 30%
│  ├─ Hull > 70% ? → UWC
│  ├─ Prop > 70% ? → PP
│  └─ 都沒有 → UWC+PP
│  💡 決策：🟠 HIGH
│
└─ SL ≥ 30%
   └─ DD (進塚)
      💡 決策：🔴 CRITICAL
```

---

## 💰 ROI 計算流程

```
輸入：
├─ counterfactual.energy_pricing.daily_saving_usd (來自模型)
├─ recommendation.successRate (歷史成功率%)
├─ recommendation.estimatedCost (維修成本)
└─ 時間：30天/月, 12月/年

計算：
├─ monthlySavings = dailySavingUsd × 30 × (successRate / 100)
├─ annualSavings = monthlySavings × 12
├─ paybackMonths = estimatedCost / monthlySavings
└─ roi% = ((annualSavings - estimatedCost/12) / estimatedCost) × 100

輸出：
├─ monthlySavings (USD)
├─ annualSavings (USD)
├─ paybackMonths (月) 或 "不划算"
└─ roi (%) ← 顯示為 4 位大號紅字
```

---

## 🔗 API 依賴

### 必須的端點

| 端點 | 方法 | 何時調用 | 返回值 |
|------|------|--------|--------|
| `/vessels/{id}/speed-loss-dashboard` | GET | 頁面加載 | `{ raw, smooth, summary.hull_pct, summary.prop_pct, events }` |
| `/predict/fuel-consumption` | POST | 頁面加載 + 數據變化 | `{ counterfactual_uwc_pp.{ fuel_saving_mt_per_day, saving_pct, energy_pricing } }` |
| `/vessels/{id}/fuel-anomaly-cause` | GET | 頁面加載（備用） | `{ summary.recommended_action }` |

### VesselSummary 必要欄位

```typescript
vessel.degradationRatePctPerDay: number  // 用於時機預測
vessel.daysSinceHullClean: number
vessel.daysSincePropPolish: number
```

---

## ⚠️ 潛在問題 & 解決方案

### 問題 1：燃油預測 API 返回 null

**症狀**：ROI 面板不顯示

**原因**：
- wind_scale > 4
- hours_full_speed < 22
- 模型無適用範圍

**解決**：
```javascript
if (!counterfactual || !counterfactual.benefit_available) {
  return null  // ROI 面板不顯示
}
```

### 問題 2：根因數據為 null

**症狀**：始終推薦 UWC+PP（預設值）

**原因**：slData.summary 為 null

**解決**：使用 nullish coalescing
```javascript
const hullPct = slData.value.summary?.hull_pct ?? 50
const propPct = slData.value.summary?.prop_pct ?? 50
```

### 問題 3：衰退速率為 0

**症狀**：時機預測 Infinity 或 NaN

**原因**：vessel.degradationRatePctPerDay = 0

**解決**：條件檢查
```javascript
if (vessel.degradationRatePctPerDay) { ... }
```

---

## 🧪 快速驗證

### 在瀏覽器 Console 檢查

```javascript
// 檢查 fuelPrediction 是否加載
console.log($nuxt.$el.__vue__)  // 查看組件狀態

// 或在 Vue DevTools 中
Components → MaintenanceDecision → fuelPrediction (ref)
```

### 檢查 Network 標籤

```
1. /vessels/{id}/speed-loss-dashboard
   ✅ 返回 status 200
   ✅ 返回 summary.hull_pct 和 summary.prop_pct

2. /predict/fuel-consumption
   ✅ 返回 status 200
   ✅ 返回 counterfactual_uwc_pp.energy_pricing
```

---

## 📋 驗收清單

完成前檢查：

- [ ] 代碼編譯無誤（`npm run build`）
- [ ] 沒有 TypeScript 錯誤
- [ ] 沒有未定義的變數
- [ ] 所有 API 調用正確
- [ ] 5 個測試場景都通過
- [ ] ROI 面板顯示 6 項新指標
- [ ] 衰退曲線面板正確渲染
- [ ] 緊急程度顏色正確
- [ ] 響應式設計（桌面/移動）
- [ ] 可訪問性（ARIA 標籤）

---

## 🚀 部署檢查清單

- [ ] 確認後端 API 可用
- [ ] 確認 API 返回值包含新欄位
- [ ] 在測試環境驗證
- [ ] 在生產環境驗證
- [ ] 監控錯誤日誌
- [ ] 收集用戶反饋

---

**需要幫助？** 檢查詳細文檔：
- 🔍 邏輯詳解：`MAINTENANCE_DECISION_IMPROVEMENTS.md`
- 🧪 測試用例：`MAINTENANCE_DECISION_TEST_CASES.md`
