# 基於污損歸因的決策建議邏輯

**核心洞察**：現在我不是用「Speed Loss 數值」做決策，而是用「船殼 vs 螺旋槳的歸因分解」

---

## 🎯 決策邏輯的根本改變

### 之前（錯誤）
```
Speed Loss = 25%
  ↓
if SL >= 20%: → UWC+PP （盲目建議）
```

**問題**：25% 的 Speed Loss 可能來自：
- 100% 來自船殼污損（應該 UWC）
- 100% 來自螺旋槳污損（應該 PP）
- 混合污損（應該 UWC+PP）
- 大部分來自天候（應該監控中）

我們不知道！

### 之後（正確）
```
Speed Loss = 25%
  ↓
計算歸因分解：
  - hull_contrib = 3.6%（來自船殼）
  - prop_contrib = 0.9%（來自螺旋槳）
  - weather_contrib = 20.5%（來自天候）
  ↓
決策邏輯：
  if hull_contrib > prop_contrib:
    → UWC （清洗為主）
  elif prop_contrib > hull_contrib:
    → PP （拋光為主）
  else:
    → 監控中或 UWI（天候為主，維修效果差）
```

---

## 📊 決策樹 — 基於歸因分解

### 輸入數據
```
From backend:
- hull_degradation = (hull_rate / 30) × days_since_hull_clean
- prop_degradation = (prop_rate / 30) × days_since_prop_polish
- current_speed_loss = observed value
```

### 決策邏輯

```python
def recommend_by_attribution(
    current_speed_loss,
    hull_degradation,          # 艦隊推算的船殼衰退
    prop_degradation,          # 艦隊推算的螺旋槳衰退
    days_since_hull_clean,
    days_since_prop_polish,
    maintenance_history        # 最近的檢查記錄
):
    """
    決策不基於「總 SL」，而基於「歸因分解」
    """
    
    # 第 1 層：檢查數據有效性
    if hull_degradation is None or prop_degradation is None:
        # 數據不足，保守做法
        if current_speed_loss >= 30:
            return "DD"
        elif current_speed_loss >= 20:
            return "UWI"  # 先做檢查了解污損
        else:
            return "監控中"
    
    # 第 2 層：分解主要原因
    total_model_contrib = hull_degradation + prop_degradation
    
    if total_model_contrib < 0.5:
        # 衰退很少，主要是天候
        return "監控中"
    
    hull_ratio = hull_degradation / total_model_contrib
    prop_ratio = prop_degradation / total_model_contrib
    
    # 第 3 層：基於污損比例決策
    if hull_ratio > 0.7:
        # 船殼污損佔 70% 以上
        if days_since_hull_clean > 200:
            return "UWC"
        elif days_since_hull_clean > 400:
            return "CRITICAL_UWC"
        else:
            return "UWI+PP"  # 最近清洗過，檢查一下螺旋槳
    
    elif prop_ratio > 0.7:
        # 螺旋槳污損佔 70% 以上
        if days_since_prop_polish > 250:
            return "PP"
        elif days_since_prop_polish > 400:
            return "CRITICAL_PP"
        else:
            return "UWI"  # 最近拋光過，檢查一下船殼
    
    else:
        # 混合污損
        if max(days_since_hull_clean, days_since_prop_polish) > 300:
            return "UWC+PP"
        elif current_speed_loss >= 30:
            return "DD"
        else:
            return "UWI"  # 先檢查，確認污損情況
    
    # 第 4 層：特殊情況
    # 如果最近做過維修但沒有改善
    latest_maint = maintenance_history[-1] if maintenance_history else None
    if latest_maint:
        days_since_latest = current_day - latest_maint.event_day
        if days_since_latest < 30:
            # 30 天內做過維修
            if latest_maint.event_type in ['UWC', 'UWC+PP']:
                # 清洗後沒改善 → 可能是基礎設施問題
                return "UWI"  # 檢查一下
```

---

## 🔑 轉換規則

| 場景 | 舊邏輯（SL 基礎） | 新邏輯（歸因基礎） | 理由 |
|------|-----------------|------------------|------|
| SL=25%, hull_deg=3.6%, prop_deg=0.9% | UWC+PP | **UWC** | 船殼為主（75:25），優先清洗 |
| SL=22%, hull_deg=0.5%, prop_deg=2.0% | UWC+PP | **PP** | 螺旋槳為主（80:20），優先拋光 |
| SL=20%, hull_deg=0.2%, prop_deg=0.1% | UWC+PP | **監控中** | 總衰退 < 0.5%，主要是天候 |
| SL=35%, hull_deg=1.5%, prop_deg=0.5% | DD | **DD** | 相同（衰退率超過艦隊限制） |
| UWI 後 SL=20% | "失敗" | **正常** | UWI 不應有改善，這是設計的 |

---

## 🔗 數據流改進

### 現在的數據流
```
Speed Loss Dashboard
  ├─ raw[i] = [day, speed_loss_pct]
  ├─ smooth[i] = [day, smooth_val, hull_contrib, prop_contrib]
  └─ summary = { hull_pct, prop_pct }

但是：hull_pct 和 prop_pct 是什麼？
是艦隊歸因模型推算的比例！
```

### 應該使用的數據
```
GET /vessels/{id}/speed-loss-attribution
  └─ fleet_calibration
      ├─ hull.slope_per_30d_pct     (艦隊船殼衰退速率)
      ├─ propeller.slope_per_30d_pct (艦隊螺旋槳衰退速率)
      └─ calibrated_on_vessels: n   (有多少艘船的數據)

GET /vessels/{id}/maintenance-latest-inspection
  ├─ event_day
  ├─ hull_fouling_type (來自 UWI 檢查)
  ├─ propeller_condition (來自 UWI 檢查)
  ├─ days_since_hull_clean
  └─ days_since_prop_polish
```

---

## ⚠️ 極其重要的差別

### 錯誤理解
```
"Speed Loss Dashboard 的 hull_pct = 船殼污損百分比"
"Speed Loss Dashboard 的 prop_pct = 螺旋槳污損百分比"

❌ 這不對！

hull_pct 和 prop_pct 是什麼？
是「歸因分解模型」對「某一個時間點」的推算，
基於艦隊衰退規律計算出來的「理論污損比例」
```

### 正確理解
```
hull_pct = 艦隊推算的船殼衰退 / 總衰退
         = 說明「假如有污損，最可能的比例」
         
這個比例用來做決策：
if hull_pct > 70%: 建議清洗
if prop_pct > 70%: 建議拋光
if 都 < 70%: 可能是天候為主，建議先檢查
```

---

## 🎯 決策建議改進方案

### 改進 1：集成艦隊衰退率
```javascript
// 在 MaintenanceDecision.vue 中
const speedLossAttribution = await getSpeedLossAttribution(props.imo)
const hullRate = speedLossAttribution.fleet_calibration.hull.slope_per_30d_pct
const propRate = speedLossAttribution.fleet_calibration.propeller.slope_per_30d_pct
```

### 改進 2：計算實際的歸因值
```javascript
const latestInspection = await getLatestInspection(props.imo)
const daysSinceHullClean = latestInspection.days_since_hull_clean
const daysSincePropPolish = latestInspection.days_since_prop_polish

// 計算歸因貢獻
const hullDegradation = (hullRate / 30) * daysSinceHullClean
const propDegradation = (propRate / 30) * daysSincePropPolish
const totalDegradation = hullDegradation + propDegradation

// 計算比例
const hullRatio = hullDegradation / totalDegradation
const propRatio = propDegradation / totalDegradation
```

### 改進 3：基於比例做決策
```javascript
if (hullRatio > 0.7) {
  recommendationType = 'UWC'  // 清洗為主
} else if (propRatio > 0.7) {
  recommendationType = 'PP'   // 拋光為主
} else if (totalDegradation < 0.5) {
  recommendationType = '監控中' // 天候為主
} else {
  recommendationType = 'UWC+PP' // 均衡
}
```

---

## 📊 實例演練

### 案例 1：船殼為主的污損

```
數據：
- current_speed_loss = 25%
- hull_rate = 0.3% per 30d
- prop_rate = 0.15% per 30d
- days_since_hull_clean = 150
- days_since_prop_polish = 30

計算：
- hull_degradation = (0.3/30) × 150 = 1.5%
- prop_degradation = (0.15/30) × 30 = 0.15%
- total = 1.65%
- hull_ratio = 1.5 / 1.65 = 91%
- prop_ratio = 0.15 / 1.65 = 9%

決策：
❌ 舊邏輯：SL=25% → UWC+PP
✅ 新邏輯：hull_ratio=91% → UWC (清洗為主)

理由：螺旋槳最近剛拋光（30天），不需要再拋；
船殼污損為主（91%），優先清洗。
```

### 案例 2：螺旋槳為主的污損

```
數據：
- current_speed_loss = 18%
- hull_rate = 0.3% per 30d
- prop_rate = 0.15% per 30d
- days_since_hull_clean = 30
- days_since_prop_polish = 180

計算：
- hull_degradation = (0.3/30) × 30 = 0.3%
- prop_degradation = (0.15/30) × 180 = 0.9%
- total = 1.2%
- hull_ratio = 0.3 / 1.2 = 25%
- prop_ratio = 0.9 / 1.2 = 75%

決策：
❌ 舊邏輯：SL=18% → UWC+PP (或根據 slData.summary)
✅ 新邏輯：prop_ratio=75% → PP (拋光為主)

理由：船殼最近清洗過（30天），污損少；
螺旋槳長時間沒拋光（180天），效率下降，優先拋光。
```

### 案例 3：天候為主

```
數據：
- current_speed_loss = 22%
- hull_rate = 0.3% per 30d
- prop_rate = 0.15% per 30d
- days_since_hull_clean = 10
- days_since_prop_polish = 10

計算：
- hull_degradation = (0.3/30) × 10 = 0.1%
- prop_degradation = (0.15/30) × 10 = 0.05%
- total = 0.15% (very small!)
- SL - (hull + prop) = 22% - 0.15% = 21.85% ← 大部分是其他因素（天候）

決策：
❌ 舊邏輯：SL=22% → UWC+PP（盲目建議維修）
✅ 新邏輯：total_degradation=0.15% < 0.5% → 監控中

理由：船殼和螺旋槳都剛維護過，衰退很小；
22% 的 SL 大多來自天候，維修不會有幫助。
```

---

## 🚀 實施步驟

1. **獲取艦隊衰退率**
   ```
   /speed-loss-attribution 返回 fleet_calibration
   ```

2. **獲取最新檢查記錄**
   ```
   /maintenance-latest-inspection 返回 days_since_*
   ```

3. **計算歸因分解**
   ```
   hull_deg = rate × days
   prop_deg = rate × days
   ```

4. **基於分解做決策**
   ```
   if hull > prop → UWC
   if prop > hull → PP
   if both small → 監控中
   if both large → UWC+PP or DD
   ```

---

這才是正確的決策邏輯！

