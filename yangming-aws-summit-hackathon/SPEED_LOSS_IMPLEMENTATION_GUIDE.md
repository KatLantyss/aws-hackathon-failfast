# Speed Loss 分析系統 - 實現指南

## 概述

本指南說明如何使用完整的 Speed Loss 計算與可視化管道，基於 ISO 19030 標準實現船舶推進效能分析。

---

## 📋 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                    數據輸入層                                 │
│  - vt_fd.csv (正午報表：15艘船 × 5年)                        │
│  - maintenance.csv (維修事件記錄)                            │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                  數據處理層                                   │
│  speed_loss_pipeline.py                                      │
│  ├─ 步驟 1：數據清洗 (移除錨泊日、處理缺失值)                 │
│  ├─ 步驟 2：計算 Daily FOC (油耗標準化)                      │
│  ├─ 步驟 3：分層計算 Speed Loss                              │
│  ├─ 步驟 4：整合維修事件                                      │
│  ├─ 步驟 5：生成統計指標                                      │
│  └─ 步驟 6：異常檢測與告警                                    │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                  結果輸出層                                   │
│  speed_loss_output/ 目錄                                     │
│  ├─ speed_loss_complete.csv (完整計算結果)                   │
│  ├─ fleet_statistics.csv (船隊統計)                          │
│  ├─ anomalies.csv (異常事件)                                 │
│  └─ visualization_data.json (可視化數據)                     │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                  可視化展示層                                 │
│  SpeedLossDashboard.vue (Vue 3 儀表板組件)                   │
│  ├─ 船隊概覽 KPI                                             │
│  ├─ 時間序列圖表                                             │
│  ├─ 維修效益驗證                                             │
│  ├─ 異常告警表格                                             │
│  ├─ 效能對比熱力圖                                           │
│  └─ 統計摘要與建議                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速開始

### 1. 執行計算管道

```bash
cd yangming-aws-summit-hackathon
python speed_loss_pipeline.py
```

**預期輸出：**
- `speed_loss_output/` 目錄包含所有計算結果

### 2. 集成到 Web 應用

在你的 Vue 應用中導入儀表板：

```vue
<template>
  <SpeedLossDashboard />
</template>

<script>
import SpeedLossDashboard from '@/components/SpeedLossDashboard.vue'

export default {
  components: {
    SpeedLossDashboard
  }
}
</script>
```

---

## 📊 Speed Loss 計算方法

### 層級 1：相對基準法（最直觀）

```
Speed Loss L1 (%) = (Daily FOC - Baseline FOC) / Baseline FOC × 100

其中：
  - Daily FOC：該日實際油耗（VLSFO 當量）
  - Baseline FOC：同船歷史最佳性能（10% 分位）
```

**應用場景：** 快速識別效能衰退趨勢，適合船隊概覽

**優勢：**
- 直觀易懂
- 無需複雜建模
- 自動納入季節性和船齡效應

### 層級 2：多因素回歸法（最精準）

```
Expected FOC = Baseline FOC × (1 + 衰退因子 + 風力因子 + 季節因子 + 負載因子)

Speed Loss L2 (%) = (Expected FOC - Actual FOC) / Expected FOC × 100
```

**因素分解：**
- **衰退因子**：`sqrt(days_since_maintenance / 365) × 15%`
  - 根據過去 UWI/DD 事件計算
  - 反映設備隨時間推移的性能衰退
  
- **風力因子**：`(WIND_SCALE / 4) ^ 1.5 × 10%`
  - 風力越強，需要更多動力
  - 非線性關係
  
- **季節因子**：`sin(2π × day / 365) × 5%`
  - 模型化季節性海況變化
  
- **負載因子**：`-(CARGO / MAX_CARGO) × 5%`
  - 負載越高，相對效率越好

**應用場景：** 控制外部變量，隔離船舶本身的效能衰退

**優勢：**
- 區分設備狀態和環境因素
- 適合預測維修時機
- 支持成本效益分析

### 層級 3：維修效益法（決策導向）

```
Maintenance Efficacy = FOC_7day_after_event - FOC_7day_before_event

Efficacy % = (FOC_before - FOC_after) / FOC_before × 100
```

**關鍵事件：**
- UWI（水下檢查）
- PP（螺旋槳拋光）
- UWC（船殼清洗）
- DD（進塢保養）

**應用場景：** 量化維修作業的實際效益，支持 ROI 分析

---

## 🔧 燃料標準化處理

系統支持多種燃料類型，統一折算為 VLSFO 當量：

| 燃料 | 熱值 (MJ/kg) | 折算因子 |
|------|:----:|:----:|
| HSHFO | 40.2 | 1.00 |
| VLSFO | 40.2 | 1.00 |
| ULSFO | 41.2 | 1.02 |
| LSMGO | 42.7 | 1.06 |
| BIO_HSFO | 39.4 | 0.98 |

**折算公式：**
```
FOC_VLSFO_equiv = FOC_fuel × LCV_fuel / LCV_VLSFO
```

---

## 📈 可視化組件說明

### KPI 卡片（船隊概覽）
- **船隊平均效能損失**：所有有效航次的平均 Speed Loss
- **最佳表現**：效能損失最低的船舶
- **需關注**：效能損失最高的船舶
- **異常事件**：過去 30 天的告警數量

### 時間序列圖表
- **藍色線（L1）**：相對基準法結果
- **綠色線（L2）**：多因素模型結果
- **灰色陰影**：維修事件標記
- **紅色區域**：異常高損失區間（>20%）

### 維修效益時間軸
- 每個維修事件顯示為可交互的卡片
- 懸停時高亮相應的 Speed Loss 變化
- 支持點擊查看詳細維修報告

### 異常告警表
- **HIGH**（紅色）：Speed Loss > 30%
- **MEDIUM**（黃色）：Speed Loss > 20% 或異常油耗
- 支持"調查"按鈕深入分析

### 效能對比熱力圖
- 橫軸：時間周期（週）
- 縱軸：船舶代號
- 顏色深度：效能損失百分比
- 支持懸停提示具體數值

---

## 🎯 使用場景

### 場景 1：日常監控
**流程：**
1. 每日運行 `speed_loss_pipeline.py`
2. 檢查異常告警表
3. 針對高損失船舶進行根因分析

**關鍵指標：** Speed Loss L1 平均值、異常計數

### 場景 2：維修計劃制定
**流程：**
1. 分析 Speed Loss L2 的衰退曲線
2. 對比歷史維修效益數據
3. 預測最佳維修時機

**關鍵指標：** 衰退因子趨勢、維修前後的效能改善

### 場景 3：船隊績效評估
**流程：**
1. 生成月度、季度船隊報告
2. 對比同型船性能
3. 識別異常船舶

**關鍵指標：** 船隊 KPI、熱力圖分佈

### 場景 4：根因分析
**流程：**
1. 從異常告警開始
2. 對比同期其他船舶數據
3. 關聯維修/天候/海況信息
4. 生成調查報告

**關鍵指標：** 風力、海況、維修距離、負載等多維特徵

---

## 📦 數據輸出詳解

### speed_loss_complete.csv
完整計算結果，包含以下關鍵欄位：

| 欄位 | 說明 |
|------|------|
| ship_id | 船舶代號 |
| NOON_UTC | 相對日數 |
| daily_foc | 實際油耗（MT/day） |
| daily_foc_vlsfo_equiv | VLSFO 當量油耗 |
| speed_loss_pct_l1 | 層級 1 效能損失 (%) |
| speed_loss_pct_l2 | 層級 2 效能損失 (%) |
| expected_foc | 預期油耗（多因素模型） |
| days_since_maintenance | 距離上次維修天數 |
| WIND_SCALE | 風力等級（0-12） |
| SPEED_THROUGH_WATER | 對水航速 (knots) |
| last_maintenance_type | 最近維修類型 |
| maintenance_improvement_pct | 該維修事件的效能改善 (%) |

### fleet_statistics.csv
船隊級別統計：

| 欄位 | 說明 |
|------|------|
| ship_id | 船舶代號 |
| days_count | 有效航次天數 |
| avg_foc | 平均油耗 |
| min_foc | 最低油耗 |
| max_foc | 最高油耗 |
| foc_std | 油耗標準差 |
| avg_speed_loss_l1 | 平均效能損失 (L1) |
| avg_speed_loss_l2 | 平均效能損失 (L2) |
| avg_wind_scale | 平均風力 |
| avg_speed_through_water | 平均對水航速 |

### anomalies.csv
異常事件日誌：

| 欄位 | 說明 |
|------|------|
| ship_id | 船舶代號 |
| day | 相對日數 |
| type | 異常類型（HIGH_SPEED_LOSS, ABNORMAL_FOC） |
| severity | 嚴重級別（HIGH, MEDIUM） |
| value | 異常數值 |
| threshold | 異常閾值 |

### visualization_data.json
用於前端可視化的結構化數據：

```json
{
  "fleet_summary": {
    "total_ships": 15,
    "total_days": 21272,
    "avg_fleet_speed_loss": 12.3,
    "worst_ship": "S8",
    "best_ship": "S1"
  },
  "timeseries": {
    "S1": {
      "days": [0, 1, 2, ...],
      "speed_loss_l1": [5.2, 6.1, 4.8, ...],
      "speed_loss_l2": [6.0, 6.5, 5.2, ...],
      "daily_foc": [85.3, 86.1, 84.5, ...]
    }
  },
  "maintenance_events": [
    {
      "ship_id": "S1",
      "day": 981,
      "event_type": "DD",
      "hull_fouling_type": "barnacle,slime"
    }
  ]
}
```

---

## 🔌 API 端點示例

如果在後端集成，可提供以下 API：

### GET /api/speed-loss/fleet-summary
返回船隊級別 KPI

### GET /api/speed-loss/ship/{ship_id}
返回特定船舶的時間序列數據

### GET /api/speed-loss/anomalies
返回異常事件列表（支持時間範圍篩選）

### GET /api/speed-loss/maintenance/{ship_id}
返回特定船舶的維修效益分析

### POST /api/speed-loss/generate-report
生成自定義報告

---

## 📝 配置參數

在 `speed_loss_pipeline.py` 中可調整以下參數：

```python
# 層級 3 計算的時間窗口（天）
MAINTENANCE_WINDOW = 30

# Speed Loss 異常告警閾值（%）
ANOMALY_THRESHOLD_L1 = 20

# FOC 異常檢測的標準差倍數
FOC_ANOMALY_SIGMA = 2

# 滾動窗口大小（天）
ROLLING_WINDOW = 7

# 基準 FOC 計算的分位點
BASELINE_QUANTILE = 0.1
```

---

## 💡 最佳實踐

### 1. 定期更新
- 每週運行一次計算管道
- 保留歷史結果以追蹤趨勢
- 定期驗證異常告警的準確性

### 2. 多層次分析
- L1 用於快速概覽
- L2 用於深度分析
- L3 用於維修決策

### 3. 上下文考量
- 考慮季節性因素（冬季效能通常更差）
- 考慮新造船的蜜月期效應
- 區分常規衰退和異常事件

### 4. 跨船對比
- 對比同型船的表現
- 識別操作差異
- 分享最佳實踐

### 5. 根因分析
- 不要僅依賴單一指標
- 整合多個數據源（天氣、海況、維修記錄）
- 與船舶操作人員溝通驗證

---

## 🐛 故障排除

### 問題：計算結果中 Speed Loss 為 NaN
**原因：** Daily FOC 缺失或為 0
**解決：** 檢查 vt_fd.csv 中的燃料欄位數據

### 問題：維修事件沒有顯示效能改善
**原因：** 維修前後數據不足或結果為負值
**解決：** 確保 maintenance.csv 中的日期格式正確；負值可能表示維修無效或數據異常

### 問題：某些船舶的統計指標為空
**原因：** 該船舶在清洗後無有效記錄
**解決：** 檢查 WIND_SCALE、HOURS_FULL_SPEED 等必需欄位的完整性

---

## 📚 參考標準

- **ISO 15016：** 船舶試航修正標準
- **ISO 19030：** 船體與螺旋槳效能量測標準
- **IMO EEDI：** 船舶設計指數（參考背景）

---

## 📞 支持與反饋

如有問題或建議，請提供：
1. 異常發生時的 `NOON_UTC` 日期
2. 涉及的船舶代號
3. 數據清洗日誌輸出
4. 預期 vs 實際結果對比

---

**最後更新：** 2026-07-15
