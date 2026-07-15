# Speed Loss 分析系統 - 快速開始指南

## 📌 核心概念（1 分鐘理解）

### 什麼是 Speed Loss？
Speed Loss 是**實際船舶性能相比最佳狀態的衰退幅度**。用百分比表示。

```
Speed Loss = (實際油耗 - 最佳狀態油耗) / 最佳狀態油耗 × 100%
```

**例子：** 
- 新造船：油耗 50 MT/day → Speed Loss = 0%（基準）
- 1年後：油耗 60 MT/day → Speed Loss = 20%（因為船體汙損、螺旋槳粗糙）
- 維修後：油耗 52 MT/day → Speed Loss = 4%（恢復大部分性能）

---

## 🚀 快速運行（3 步）

### 步驟 1：準備數據
確保你有兩個 CSV 文件在同一目錄：
- `vt_fd.csv` — 正午報表（15艘船 × 5年）
- `maintenance.csv` — 維修事件記錄

### 步驟 2：執行計算
```bash
python speed_loss_pipeline.py
```

等待 2-3 分鐘，輸出會生成到 `speed_loss_output/` 目錄

### 步驟 3：查看結果
```bash
cd speed_loss_output
# 查看船隊統計
cat fleet_statistics.csv

# 查看異常事件
cat anomalies.csv

# 用 Excel 或其他工具打開 speed_loss_complete.csv
```

---

## 📊 理解輸出文件

### 1️⃣ fleet_statistics.csv — 船隊概覽
告訴你每艘船的整體表現：

| 船舶 | 平均油耗 | 平均 Speed Loss | 評估 |
|------|---------|-----------------|------|
| S1 | 48.96 MT/day | 12.3% | 良好 |
| S5 | 60.85 MT/day | 15.7% | 需關注 |
| S8 | 47.95 MT/day | 9.8% | 優秀 |

**如何使用：** 快速識別表現最好和最差的船舶

### 2️⃣ anomalies.csv — 異常告警
標記每個異常日期：

| 船舶 | 日期 | 類型 | 嚴重性 | 值 |
|------|------|------|--------|-----|
| S5 | Day 450 | HIGH_SPEED_LOSS | HIGH | 35% |
| S8 | Day 600 | ABNORMAL_FOC | MEDIUM | 120 MT |

**如何使用：** 深入調查那些高 Speed Loss 的日期

### 3️⃣ speed_loss_complete.csv — 完整數據
每一行是一個航日的詳細計算結果（20,000+ 行）

關鍵欄位：
- `ship_id` — 船舶代號
- `NOON_UTC` — 日期
- `daily_foc` — 該日油耗（MT/day）
- `speed_loss_pct_l1` — 效能損失百分比
- `WIND_SCALE` — 風力等級（影響因素）
- `last_maintenance_type` — 最後的維修類型
- `days_since_last_maintenance` — 距離上次維修的天數

**如何使用：** 做進階分析、繪製趨勢圖、找出規律

### 4️⃣ visualization_data.json — 可視化數據
用於儀表板前端的結構化數據（見下文）

---

## 🎨 集成前端儀表板

### 方式 1：Vue 3 應用
直接在你的 Vue 應用中使用組件：

```vue
<template>
  <SpeedLossDashboard />
</template>

<script setup>
import SpeedLossDashboard from '@/components/SpeedLossDashboard.vue'
</script>
```

### 方式 2：其他框架
使用 JSON 數據自行繪製圖表：

```javascript
// 讀取 visualization_data.json
const data = await fetch('./speed_loss_output/visualization_data.json').then(r => r.json())

// 訪問船隊統計
console.log(data.fleet_summary)

// 訪問單船時間序列
console.log(data.timeseries['S1'])

// 訪問維修事件
console.log(data.maintenance_events)
```

---

## 🔍 三層分析方法

### 層級 1：相對基準法（最快）
```
Speed Loss L1 = (Daily FOC - 該船歷史最佳 FOC) / 基準 FOC × 100%
```
**用途：** 快速識別衰退  
**優點：** 無需複雜建模，直觀易懂  
**看那個欄位：** `speed_loss_pct_l1`

### 層級 2：多因素法（最準）
```
Expected FOC = 基準 × (1 + 設備衰退 + 風力 + 季節 + 負載)
Speed Loss L2 = (Expected - Actual) / Expected × 100%
```
**用途：** 控制環境因素，隔離設備狀態  
**優點：** 排除風力、季節等干擾，更準確  
**看那個欄位：** `speed_loss_pct_l2`

### 層級 3：維修效益法（最實用）
```
效益 = (維修前 FOC - 維修後 FOC) / 維修前 FOC × 100%
```
**用途：** 評估維修作業是否有效  
**優點：** 量化 ROI，支持維修決策  
**看那個欄位：** `maintenance_improvement_pct`

---

## 💡 使用案例

### 案例 1：發現 S5 油耗異常
1. 在 `fleet_statistics.csv` 看到 S5 的平均油耗最高（60.85 MT/day）
2. 打開 `speed_loss_complete.csv`，篩選 `ship_id == 'S5'`
3. 發現最近 100 天的 Speed Loss 維持在 15-20% 高位
4. 檢查 `last_maintenance_type` — 發現距離上次 UWI 已經 200 天
5. **決策：** 建議安排水下檢查

### 案例 2：驗證維修效果
1. 在 `anomalies.csv` 看到 S8 在 Day 500 有異常高 Speed Loss (35%)
2. 在 `speed_loss_complete.csv` 中檢查 Day 500 附近的維修事件
3. 發現 Day 480 有一次 "UWI+PP" 維修
4. **分析：** 維修 20 天後仍未恢復，可能維修質量有問題
5. **決策：** 考慮安排二次檢查

### 案例 3：季節性分析
1. 比較同季節不同年份的 S1 Speed Loss
2. 對比 `WIND_SCALE` 和 `days_since_last_maintenance`
3. 發現冬季風浪大時，Speed Loss 增加 5-8%
4. **決策：** 冬季前提前安排維修

---

## 🔧 常見問題

### Q1: Speed Loss 為什麼這麼高？
**A:** 可能原因：
- 船舶新造 - 蜜月期效應
- 需要維修 - 檢查 `days_since_last_maintenance`
- 航行條件差 - 檢查 `WIND_SCALE` 和 `SEA_HEIGHT`
- 數據異常 - 檢查 `daily_foc` 是否合理

### Q2: 如何區分"正常衰退"和"異常"？
**A:** 
- 正常：Speed Loss 每月增加 0.5-1%（線性衰退）
- 異常：速度突增或負值（檢查維修事件或數據質量）
- 用 L2 分析有助於排除環境干擾

### Q3: 每多久運行一次計算？
**A:** 推薦周期：
- 日常監控：每週一次
- 統計分析：每月一次
- 年度報告：每年一次
- 維修後：立即驗證

### Q4: 如何解釋負的 Speed Loss？
**A:** 
- 通常不會出現（已 clip 在 0% 以上）
- 如果出現：表示性能超過歷史最佳（數據異常或模型參數需調整）

---

## 📈 監控儀表板的 5 個關鍵指標

| 指標 | 目標 | 警告線 | 臨界 |
|------|------|--------|------|
| 船隊平均 Speed Loss | <10% | 15% | >20% |
| 單船 Speed Loss | <8% | 12% | >18% |
| 異常事件數 | 0 | <5/周 | >10/周 |
| 平均維修效益 | >10% | >5% | <3% |
| 維修間隔天數 | 180-365 | <180 | <120 |

---

## 📞 技術支持

### 查看計算日誌
查看標準輸出或錯誤信息

### 數據驗證
```python
import pandas as pd
df = pd.read_csv('speed_loss_output/speed_loss_complete.csv')
print(df.describe())  # 數據統計
print(df[df['daily_foc'] < 5])  # 找異常低值
```

### 性能調整
編輯 `speed_loss_pipeline.py` 中的參數：
```python
ANOMALY_THRESHOLD_L1 = 20  # Speed Loss 告警閾值
BASELINE_QUANTILE = 0.15  # 基準計算分位點
ROLLING_WINDOW = 7  # 滾動窗口天數
```

---

## 📚 相關標準文檔

詳見 `SPEED_LOSS_IMPLEMENTATION_GUIDE.md`

---

**版本：** 1.0  
**最後更新：** 2026-07-15
