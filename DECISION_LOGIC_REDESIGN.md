# 決策建議邏輯重新設計 — 基於真實維修數據

**分析日期**：2026-07-17  
**數據來源**：maintenance.csv (77 個真實維修事件)

---

## 🔍 真實數據發現

### 維修類型分布（現狀）
```
UWI+PP      40.3%  ⭐ 最常見（檢查 + 拋光）
UWI         15.6%  📋 純檢查
PP          14.3%  🔧 單獨拋光
DD          13.0%  🚢 進塢
UWC+PP       9.1%  🧼 清洗 + 拋光
UWC          7.8%  🧼 單獨清洗
```

### 關鍵數據
- **複合維修佔 49.4%** → 表示大多數情況需要多個操作
- **純檢查佔 15.6%** → 真的有很多純檢查（無物理介入）
- **船體污損類型**：
  - Slime (黏液) — 最多，需要清洗或拋光
  - Barnacle (貝類) — 次多，需要清洗或拋光
  - Algae (藻類) — 較常見
  - Calcium — 少見，可能需要專業清洗

- **螺旋槳狀況**：
  - Good: 36 次 (46.8%)
  - Fair: 5 次 (6.5%)
  - Poor: 4 次 (5.2%)
  - 未記錄: 32 次 (41.6%)

---

## ❌ 現有邏輯的問題

我之前的決策基於**單純的 Speed Loss 數值**：

```javascript
if (SL >= 30%) → DD
else if (SL >= 20%) → 根據 Hull/Prop 比例
else → UWC+PP
```

**問題**：
1. ❌ 忽視了維修記錄中的「實際污損類型」
2. ❌ 忽視了螺旋槳「實際狀況」
3. ❌ 沒有區別「純檢查」和「實際維修」
4. ❌ 沒有根據「距離上次維修的時間」來判斷

---

## ✅ 改進的決策邏輯 — 三層判斷

### 第 1 層：根據「維修記錄」判斷污損型態

```python
def analyze_maintenance_history(maintenance_records):
    """
    從歷史維修記錄判斷當前最可能的污損類型
    """
    
    # 分析最近的維修記錄
    recent_inspections = [
        m for m in maintenance_records 
        if m.event_type in ['UWI', 'UWI+PP', 'UWC', 'UWC+PP']
        and (today - m.event_day) < 180  # 最近 6 個月的檢查
    ]
    
    if not recent_inspections:
        return "未知", None
    
    latest_inspection = recent_inspections[-1]
    
    # 根據最新檢查記錄判斷污損類型
    hull_fouling = latest_inspection.hull_fouling_type  # 船體污損
    prop_condition = latest_inspection.propeller_condition  # 螺旋槳狀況
    
    return hull_fouling, prop_condition
```

### 第 2 層：根據「污損記錄 + 螺旋槳狀況」決定維修類型

```python
def recommend_maintenance_v2(
    speed_loss_pct,
    hull_fouling_type,  # 來自 UWI 檢查
    propeller_condition,  # 來自 UWI 檢查
    days_since_last_cleaning,
    days_since_last_polish
):
    """
    基於真實的污損和螺旋槳狀況做決策
    """
    
    # 污損判斷
    has_hull_fouling = hull_fouling_type and len(hull_fouling_type) > 0
    has_prop_issue = propeller_condition in ['Fair', 'Poor']
    
    # 決策邏輯 — 基於污損實況
    if speed_loss_pct >= 30:
        return "DD"  # 嚴重污損 → 進塚
    
    if has_hull_fouling and has_prop_issue:
        # 船體有污損 + 螺旋槳有問題 → UWC+PP
        return "UWC+PP"
    elif has_hull_fouling:
        # 只有船體污損
        if "slime" in hull_fouling_type or "barnacle" in hull_fouling_type:
            # 黏液/貝類 → 優先清洗
            return "UWC"
        elif "algae" in hull_fouling_type or "calcium" in hull_fouling_type:
            # 藻類/鈣 → 可能需要拋光
            return "UWC+PP"
    elif has_prop_issue:
        # 只有螺旋槳問題 → 拋光
        return "PP"
    else:
        # 沒有污損 → 監控中
        return "監控中"
```

### 第 3 層：根據「上次維修距離」調整建議

```python
def adjust_by_maintenance_interval(
    recommended_type,
    days_since_last_cleaning,
    days_since_last_polish,
    speed_loss_trend  # 衰退速率
):
    """
    根據距離上次維修的時間調整建議的緊急程度
    """
    
    # 典型的維修周期（基於數據分析）
    typical_intervals = {
        'cleaning': 150,  # 清洗通常 150 天後開始衰退
        'polish': 200,    # 拋光通常 200 天後開始衰退
    }
    
    urgency = "LOW"
    
    if recommended_type == "UWC":
        if days_since_last_cleaning > 150:
            urgency = "MEDIUM"
        if days_since_last_cleaning > 250:
            urgency = "HIGH"
        if days_since_last_cleaning > 400:
            urgency = "CRITICAL"
    
    elif recommended_type == "PP":
        if days_since_last_polish > 180:
            urgency = "MEDIUM"
        if days_since_last_polish > 300:
            urgency = "HIGH"
    
    elif recommended_type == "UWC+PP":
        max_days = max(days_since_last_cleaning, days_since_last_polish)
        if max_days > 200:
            urgency = "MEDIUM"
        if max_days > 350:
            urgency = "HIGH"
    
    return urgency
```

---

## 📋 新決策流程圖

```
船舶進入決策頁面
    ↓
讀取維修歷史 (maintenance.csv)
    ↓
找到最近的 UWI/檢查事件
    ↓
提取污損記錄：
├─ hull_fouling_type (slime/barnacle/algae/calcium)
├─ propeller_condition (Good/Fair/Poor)
└─ 檢查日期
    ↓
結合 Speed Loss % 判斷
    ├─ 如果 SL >= 30% → DD
    ├─ 如果 hull_fouling + prop_issue → UWC+PP
    ├─ 如果 只有 hull_fouling → 判斷污損類型
    │  ├─ slime/barnacle → UWC (清洗)
    │  └─ algae/calcium → UWC+PP (可能需要拋光)
    ├─ 如果 只有 prop_issue → PP
    └─ 否則 → 監控中
    ↓
根據上次維修時間調整緊急程度
    ├─ 距離上次清洗 > 150 天 → 提高優先級
    ├─ 距離上次拋光 > 200 天 → 提高優先級
    └─ 考慮衰退速率
    ↓
生成建議
```

---

## 🛠️ 代碼改進清單

### 需要修改
1. **後端**：`backend-api/handler.py`
   - 添加函數：`get_latest_inspection()` — 從維修記錄中獲取最新檢查
   - 添加函數：`analyze_hull_fouling()` — 分析污損類型特徵
   - 修改 API 返回值，包含上次維修的污損詳情

2. **前端**：`MaintenanceDecision.vue`
   - 調用新的 API 獲取檢查記錄
   - 基於污損類型重構決策邏輯
   - 添加污損類型視覺化

### 新增 API 端點
```
GET /vessels/{id}/maintenance-latest-inspection
返回：{
  event_day: number,
  event_type: string,
  hull_fouling_type: string,
  propeller_condition: string,
  days_since_inspection: number,
  days_since_cleaning: number,
  days_since_polish: number
}
```

---

## 📊 新舊邏輯對比

| 場景 | 舊邏輯 | 新邏輯 |
|------|--------|--------|
| SL=25%, Hull有slime, Prop=Good | UWC+PP | ⬆️ UWC（針對污損類型） |
| SL=18%, Hull有barnacle, Prop=Fair | UWC+PP | ⬆️ UWC+PP（因為Prop有問題） |
| SL=12%, 無污損記錄 | UWC+PP | ⬆️ 監控中（無污損證據） |
| SL=35%, Hull有多種污損 | DD | DD（保持） |
| 距上次清洗 400 天，SL=15% | 監控中 | ⬆️ HIGH（基於維修周期） |

---

## 🎯 改進效果

### 前改進期望
- ✅ **準確度提升** — 基於檢查記錄而非單純 SL 值
- ✅ **減少過度維修** — 避免無污損時的無謂清洗
- ✅ **針對性強** — slime vs barnacle → UWC，propeller issue → PP
- ✅ **時間感知** — 考慮維修周期衰退

---

**下一步**：
1. 確認後端是否可提供最新檢查記錄
2. 修改前端邏輯基於污損類型而非單純 SL%
3. 測試 5 個典型場景

