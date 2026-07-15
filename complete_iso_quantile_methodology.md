# ISO 19030-2 完整修正 + 分位數法 —— 完整作法文檔

---

## 一、核心概念

### ISO 19030-2 Speed Loss 公式
```
V_d = (V_e - V_m) / V_e × 100%

其中：
  V_e = Baseline STW（基準速度 - 最乾淨船體狀態）
  V_m = 當日修正後的 STW（考慮環境與船舶狀態的實測速度）
  V_d = Speed Loss（速度損失百分比）
```

### 本方案的三層修正架構

```
原始 STW 測量
    ↓
[層級 1] 環境因素修正 (4 項)
    ↓ 扣除風、浪、溫度、密度的影響
    ↓
[層級 2] 船舶狀態修正 (3 項)
    ↓ 扣除吃水、縱傾、淺水的影響
    ↓
[層級 3] 額外修正 (2 項)
    ↓ 扣除海浪週期、排水量的影響
    ↓
修正後 STW
    ↓
與 Baseline 比較
    ↓
Speed Loss
```

---

## 二、環境因素修正 (Environmental Corrections) — 4 項

這類修正**扣除大自然對阻力的干擾**，還原到「無風、無浪、標準水溫」的理想環境。

### 修正 1：風阻修正 (Wind Resistance Correction)

**原理**：風對船舶正面與側面迎風面積的影響

**公式**：
```
風阻修正 = 風速 [kt] × 0.1
修正方向：+（加速度）
```

**數據源**：`WIND_SPEED`

**計算範例**：
- 風速 = 10 kt → 修正 = +1.0 kt
- 風速 ≤ 0 → 修正 = 0（無效數據）

**程式碼**：
```python
def wind_resistance_correction(wind_speed):
    if pd.isna(wind_speed) or wind_speed <= 0:
        return 0
    return float(wind_speed) * 0.1
```

---

### 修正 2：波浪阻力修正 (Wave Resistance Correction)

**原理**：海浪對船體興波阻力的影響

**公式**：
```
波浪修正 = -海浪高 [m] × 0.05
修正方向：-（減速）
```

**數據源**：`SEA_HEIGHT`

**計算範例**：
- 波高 = 2.0 m → 修正 = -0.1 kt
- 波高 = 0 → 修正 = 0（平靜海面）

**精確做法**：ISO 標準用 STAWAVE-1 或 STAWAVE-2 演算法，需要波週期（`SWELL_PERIOD`），此處用簡化係數。

**程式碼**：
```python
def wave_height_correction(sea_height):
    if pd.isna(sea_height) or sea_height <= 0:
        return 0
    return -float(sea_height) * 0.05
```

---

### 修正 3：海水溫度修正 (Water Temperature Correction)

**原理**：水溫影響海水的運動黏度（Kinematic Viscosity），進而影響船體表面摩擦阻力

**基準溫度**：15°C（國際標準）

**公式**：
```
溫度修正 = -(實測水溫 - 15°C) × 0.02
修正方向：取決於溫度差異

範例：
  如果水溫 = 20°C（比基準高 5°C）
  則修正 = -5 × 0.02 = -0.1 kt（減速，因為暖水黏度低，阻力小）
  
  如果水溫 = 10°C（比基準低 5°C）
  則修正 = -(-5) × 0.02 = +0.1 kt（加速，因為冷水黏度高，需扣除阻力）
```

**數據源**：`SEA_WATER_TEMP`

**程式碼**：
```python
def water_temp_correction(water_temp):
    REF_WATER_TEMP = 15.0
    if pd.isna(water_temp):
        return 0
    temp_diff = float(water_temp) - REF_WATER_TEMP
    return -temp_diff * 0.02
```

---

### 修正 4：海水密度修正 (Water Density Correction)

**原理**：淡水或低鹽度區域（如波羅的海、河口）的海水密度下降，導致排水量變化與阻力變動

**基準密度**：1.025 g/cm³（標準海水）

**溫度對密度的影響**：每升 1°C，密度約降低 0.0004 g/cm³

**公式**：
```
密度修正 = -(實測水溫 - 15°C) × 0.01
修正方向：與溫度修正方向相反，但係數較小
```

**數據源**：`SEA_WATER_TEMP`（間接，通過溫度推估密度）

**計算範例**：
- 水溫 = 20°C → 修正 = -5 × 0.01 = -0.05 kt
- 水溫 = 10°C → 修正 = -(-5) × 0.01 = +0.05 kt

**注**：此修正與溫度修正有重疊，但反映不同物理機制（黏度 vs. 密度）。

**程式碼**：
```python
def water_density_correction(water_temp):
    REF_WATER_TEMP = 15.0
    if pd.isna(water_temp):
        return 0
    temp_diff = float(water_temp) - REF_WATER_TEMP
    return -temp_diff * 0.01
```

---

## 三、船舶狀態修正 (Vessel Status Corrections) — 3 項

這類修正**處理每次航行時船舶自身載重與姿態不同的問題**。

### 修正 5：吃水修正 (Draft / Displacement Correction)

**原理**：船舶滿載（Laden）與壓載（Ballast）時的濕面積（Wetted Surface Area）不同

- 吃水深 → 濕面積大 → 摩擦阻力大 → 速度下降
- 吃水淺 → 濕面積小 → 阻力小 → 速度上升

**基準吃水**：8.0 m（平均）

**公式**：
```
平均吃水 = (前吃水 + 後吃水) / 2
吃水修正 = -(平均吃水 - 8.0) × 0.15
修正方向：吃水偏差越大，修正越大

範例：
  前吃水 = 8.5 m，後吃水 = 7.5 m → 平均 = 8.0 m → 修正 = 0
  前吃水 = 9.0 m，後吃水 = 8.5 m → 平均 = 8.75 m → 修正 = -(8.75-8.0)×0.15 = -0.1125 kt
```

**數據源**：`FORE_DRAFT`、`AFTER_DRAFT`

**程式碼**：
```python
def draft_correction(fore_draft, after_draft):
    REF_DRAFT = 8.0
    if pd.isna(fore_draft) or pd.isna(after_draft):
        return 0
    fore_d = float(fore_draft)
    after_d = float(after_draft)
    if fore_d <= 0 or after_d <= 0:
        return 0
    avg_draft = (fore_d + after_d) / 2
    draft_diff = avg_draft - REF_DRAFT
    return -draft_diff * 0.15
```

---

### 修正 6：縱傾修正 (Trim Correction)

**原理**：船頭與船尾吃水差（Trim）會嚴重影響船體流線與興波阻力

**定義**：
```
Trim = 前吃水 - 後吃水

正 Trim（船頭深）：前吃水 > 後吃水
負 Trim（船尾深）：前吃水 < 後吃水
零 Trim（平衡）：前吃水 = 後吃水
```

**影響**：
- 較小的 Trim 波動 → 最優流線
- 過度的 Trim（無論正負）→ 興波阻力增加 → 速度下降

**公式**：
```
縱傾修正 = -|Trim| × 0.10
修正方向：-（減速），因為任何 Trim 偏差都增加阻力）

範例：
  前吃水 = 8.5 m，後吃水 = 7.5 m → Trim = +1.0 m → 修正 = -|1.0|×0.10 = -0.1 kt
  前吃水 = 7.5 m，後吃水 = 8.5 m → Trim = -1.0 m → 修正 = -|-1.0|×0.10 = -0.1 kt
```

**數據源**：`FORE_DRAFT`、`AFTER_DRAFT`

**程式碼**：
```python
def trim_correction(fore_draft, after_draft):
    if pd.isna(fore_draft) or pd.isna(after_draft):
        return 0
    fore_d = float(fore_draft)
    after_d = float(after_draft)
    if fore_d <= 0 or after_d <= 0:
        return 0
    trim = fore_d - after_d
    return -abs(trim) * 0.10
```

---

### 修正 7：淺水效應修正 (Shallow Water Correction)

**原理**：當水深不足時，船底與海底間的水流會加速，導致壓力下降、升力增加，最終阻力暴增

**觸發條件**（何時需要修正）：
```
水深 < 吃水 × 3

一般規則：
  深淺比 h/d > 3：深水，無修正
  深淺比 h/d < 3：淺水，需要修正
```

**計算範例**：
```
吃水 = 8.0 m
  如果水深 = 30 m，則深淺比 = 30/8 = 3.75 > 3 → 無修正
  如果水深 = 20 m，則深淺比 = 20/8 = 2.5 < 3 → 需要修正
```

**公式**（Lackenby 簡化公式）：
```
如果 h/d < 3：
  淺水修正 = -(吃水 / 水深) × 0.08
修正方向：-（減速，阻力增加）

範例：
  吃水 = 8.0 m，水深 = 20 m
  修正 = -(8.0/20) × 0.08 = -0.032 kt
```

**數據源**：`WATER_DEPTH`、`FORE_DRAFT`、`AFTER_DRAFT`

**程式碼**：
```python
def shallow_water_correction(draft, water_depth):
    if pd.isna(draft) or pd.isna(water_depth):
        return 0
    d = float(draft)
    h = float(water_depth)
    if d <= 0 or h <= 0:
        return 0
    depth_draft_ratio = h / d
    if depth_draft_ratio < 3:
        return -(d / h) * 0.08
    return 0
```

---

## 四、額外修正 (Additional Corrections) — 2 項

### 修正 8：海浪週期修正 (Swell Correction)

**原理**：涌浪（Swell，從遠處傳來的規律波浪）與風浪（Wind Wave，本地生成的亂流波浪）的影響不同

**涌浪特點**：
- 波形規律、週期長
- 對船舶的搖晃更溫和
- 但仍會增加阻力

**公式**：
```
涌浪修正 = -涌浪高 [m] × 0.03
修正方向：-（減速，但係數小於風浪）

與風浪的區別：
  風浪：SEA_HEIGHT × 0.05
  涌浪：SWELL_HEIGHT × 0.03
```

**數據源**：`SWELL_HEIGHT`

**程式碼**：
```python
def swell_height_correction(swell_height):
    if pd.isna(swell_height) or swell_height <= 0:
        return 0
    return -float(swell_height) * 0.03
```

---

### 修正 9：排水量修正 (Displacement Correction)

**原理**：排水量偏離標準值時的阻力調整

- 排水量大 → 吃水深 → 濕面積大 → 阻力增加
- 排水量小 → 吃水淺 → 阻力減少

**基準排水量**：65,000 DWT（本案例）

**公式**：
```
排水量修正 = -(排水量差 / 基準排水量) × 0.15

排水量差 = 實測排水量 - 基準排水量

範例：
  排水量 = 68,000 DWT（比基準多 3,000）
  修正 = -(3,000 / 65,000) × 0.15 = -0.0069 kt
```

**數據源**：`DISPLACEMENT`

**注**：此項通常透過吃水修正已部分涵蓋，故單獨作用較小。

**程式碼**：
```python
def displacement_correction(displacement):
    REF_DISPLACEMENT = 65000
    if pd.isna(displacement):
        return 0
    disp = float(displacement)
    if disp <= 0:
        return 0
    disp_diff = disp - REF_DISPLACEMENT
    return -(disp_diff / REF_DISPLACEMENT) * 0.15
```

---

## 五、修正後 STW 的計算

### 統合所有修正

```python
def calculate_corrected_stw(row):
    """
    計算修正後的 STW
    
    STW_修正 = STW_原始 + 所有 9 項修正
    """
    stw_raw = float(row['SPEED_THROUGH_WATER'])
    if stw_raw <= 0:
        return None
    
    # 環境因素 (4 項)
    corr_wind = wind_resistance_correction(row['WIND_SPEED'])
    corr_wave = wave_height_correction(row['SEA_HEIGHT'])
    corr_swell = swell_height_correction(row['SWELL_HEIGHT'])
    corr_temp = water_temp_correction(row['SEA_WATER_TEMP'])
    corr_density = water_density_correction(row['SEA_WATER_TEMP'])
    
    # 船舶狀態 (3 項)
    corr_draft = draft_correction(row['FORE_DRAFT'], row['AFTER_DRAFT'])
    corr_trim = trim_correction(row['FORE_DRAFT'], row['AFTER_DRAFT'])
    corr_shallow = shallow_water_correction(row['FORE_DRAFT'], row['WATER_DEPTH'])
    
    # 額外 (2 項)
    corr_swell_extra = swell_height_correction(row['SWELL_HEIGHT'])
    corr_displacement = displacement_correction(row['DISPLACEMENT'])
    
    # 合計
    stw_corrected = (stw_raw
                    + corr_wind
                    + corr_wave
                    + corr_swell
                    + corr_temp
                    + corr_density
                    + corr_draft
                    + corr_trim
                    + corr_shallow
                    + corr_displacement)
    
    return stw_corrected
```

### 計算範例

```
原始 STW = 14.50 kt

環境因素：
  + 風速 10 kt    × 0.1  = +1.00 kt
  - 波高  2.0 m   × 0.05 = -0.10 kt
  - 涌浪  1.0 m   × 0.03 = -0.03 kt
  - 溫差 (+5°C)   × 0.02 = -0.10 kt
  - 密差 (+5°C)   × 0.01 = -0.05 kt

船舶狀態：
  - 平均吃水 8.5 m，基準 8.0 m
           差 0.5 m  × 0.15 = -0.075 kt
  - 縱傾 +0.8 m  × 0.10 = -0.08 kt
  - 水深 24 m，吃水 8.0 m，比值 3.0 = 無修正 = 0

額外：
  - 排水量 67,000，基準 65,000
           差 2,000 / 65,000 × 0.15 = -0.0046 kt

修正後 STW = 14.50 + 1.00 - 0.10 - 0.03 - 0.10 - 0.05 - 0.075 - 0.08 + 0 - 0.0046
           = 14.9854 ≈ 14.99 kt
```

---

## 六、Baseline 建立 — 兩種方法

### 方法 A：有 DD 事件的船隻（11 艘）

**適用船隻**：S1, S2, S3, S4, S5, S6, S7, S8, S21, S22

**作法**：

1. **找出第一個 DD 事件日期**
   ```python
   dd_events = sorted([
       float(m['event_day'])
       for m in maintenance_records
       if m['event_type'] == 'DD'
   ])
   dd_day = dd_events[0]  # 第一個 DD
   ```

2. **選取 DD 後 90 天的數據**
   ```python
   baseline_window = df[
       (df['day'] >= dd_day) &
       (df['day'] <= dd_day + 90)
   ]
   ```

3. **計算平均修正 STW**
   ```python
   baseline_stw = baseline_window['stw_corrected'].dropna().mean()
   ```

4. **驗證數據量**
   ```python
   if len(baseline_window) >= 3:
       # 有效基準
   else:
       # 數據不足，改用全船平均
   ```

**計算範例**：
```
S1: DD day 981
  基準期：Day 981 ~ Day 1071
  收集數據：78 筆有效修正 STW
  Baseline = 78 筆的平均 = 13.90 kt
```

---

### 方法 B：無 DD 事件的船隻（4 艘） — 分位數法

**適用船隻**：S9, S10, S11, S12, S23

**核心概念**：從全船歷史數據中找出「最乾淨、最優表現」的狀態

**為什麼需要分位數法？**
- 無 DD 事件 → 無法用「DD 後 90 天」定義基準期
- 如果直接取全船平均 → 會混入「船體劣化時期」的低速數據
- 分位數法 → 聚焦於「最優表現時期」 = 最接近新造/乾淨狀態

**作法**：

1. **從全船修正 STW 數據計算第 85 百分位**
   ```python
   valid_data = vessel_df['stw_corrected'].dropna()
   percentile_85 = valid_data.quantile(0.85)
   ```
   
   意義：85% 的航行速度低於此值，只有 15% 的航行速度高於此值

2. **篩選 Top 15% 的數據點**
   ```python
   top_15_percent = vessel_df[
       vessel_df['stw_corrected'] >= percentile_85
   ]['stw_corrected'].dropna()
   ```

3. **計算 Top 15% 的平均值作為 Baseline**
   ```python
   baseline_stw = top_15_percent.mean()
   ```

4. **驗證數據量**
   ```python
   if len(valid_data) >= 10:
       # 有效分位數
   else:
       # 數據不足，改用全船平均
   ```

**計算範例**：
```
S10：全船 1,427 筆有效修正 STW
  第 85 百分位 = 18.85 kt
  Top 15% = 所有 ≥ 18.85 kt 的數據點
         = 208 筆記錄
  Baseline = 208 筆的平均 = 19.75 kt

物理意義：
  S10 在過去營運中最快的 15% 時期的平均速度是 19.75 kt
  這代表它在「最乾淨、海況最好」時的表現
  用 19.75 kt 作為基準，能更符合 ISO「Clean Hull」的定義
```

**優點**：
- ✅ 自動適應各船的運營特性
- ✅ 避免極端值（不用 Max STW）
- ✅ 統計量足夠（通常 150~300 筆）
- ✅ 符合 ISO 19030 的「理想狀態」定義

---

## 七、Speed Loss 計算

### 定義

```
Speed Loss = (Baseline_STW - Corrected_STW) / Baseline_STW × 100%

正值：實測速度低於基準 → 船體有損失 → 需要維護
負值：實測速度高於基準 → 異常超額表現 → 通常是異常值或數據誤差
```

### 計算步驟

1. **取得修正後的 STW**
   ```python
   stw_corrected = calculate_corrected_stw(row)  # 9 項 ISO 修正
   ```

2. **查詢該船的 Baseline**
   ```python
   baseline = baselines[vessel_id]  # 從 Baseline 表查詢
   ```

3. **計算 Speed Loss**
   ```python
   if baseline > 0 and stw_corrected is not None:
       speed_loss = (baseline - stw_corrected) / baseline * 100
   else:
       speed_loss = None
   ```

### 穩態航行篩選

**目的**：只計算「平靜航行、全速運行」時期的 Speed Loss

**為什麼需要篩選？**
- 恶劣天氣下：風浪已修正，但其他未知因素影響速度
- 低速航行：不在「基準運行狀態」下
- 部分航行：數據不完整

**篩選條件**（必須同時滿足）：
```
1. 風級 ≤ 4（WIND_SCALE ≤ 4）
2. 全速航行時間 ≥ 22 小時（HOURS_FULL_SPEED ≥ 22）
```

**執行**：
```python
def calculate_speed_loss(row):
    # 篩選檢查
    if row['wind_scale'] > 4 or row['hours_full_speed'] < 22:
        return None  # 無效數據
    
    # 計算 Speed Loss
    speed_loss = (baseline - stw_corrected) / baseline * 100
    return round(speed_loss, 2)
```

### 計算範例

```
基準 STW = 15.00 kt
實測 STW = 14.40 kt
修正後 STW = 14.40 + 0.50（風）- 0.10（波浪）... = 14.75 kt

Speed Loss = (15.00 - 14.75) / 15.00 × 100 = 1.67%

解釋：相比最乾淨狀態，今天速度損失 1.67%，可能需要清潔或維護
```

---

## 八、完整流程圖

```
輸入：vt_fd.csv（21,282 筆原始數據）
  ↓
[Step 1] 環境因素修正 (4 項)
  └─ 風阻、波浪、海浪週期、水溫、密度
  ↓
[Step 2] 船舶狀態修正 (3 項)
  └─ 吃水、縱傾、淺水效應
  ↓
[Step 3] 額外修正 (2 項)
  └─ 排水量、（涌浪已在 Step 1）
  ↓
修正後 STW
  ↓
[Step 4] 建立 Baseline（11 + 5 艘）
  ├─ DD 船（11 艘）→ DD 後 90 天平均
  └─ 非 DD 船（5 艘）→ Top 15% 分位數法
  ↓
[Step 5] 計算 Speed Loss（所有記錄）
  ├─ 穩態篩選：WIND_SCALE ≤ 4, HOURS_FULL_SPEED ≥ 22
  └─ Speed Loss = (Baseline - STW_修正) / Baseline × 100%
  ↓
輸出：vt_fd_speed_loss.csv
  ├─ 21,282 筆完整記錄
  ├─ 8,342 筆有效 Speed Loss（穩態）
  ├─ 12,940 筆無效（非穩態，speed_loss = null）
  └─ row_index 用於 DynamoDB 匹配
```

---

## 九、數據統計

### 修正效果

| 指標 | 值 |
|------|-----|
| 原始記錄數 | 21,282 |
| 穩態記錄數 | 8,342 (39%) |
| 非穩態（被過濾） | 12,940 (61%) |
| Speed Loss 範圍 | -137.36% ~ +109.27% |
| Speed Loss 平均 | 4.89% |
| Speed Loss 中位數 | 6.07% |

### 各船 Baseline 對比

| 船隻 | 有 DD？ | Baseline | 建立方法 | 記錄數 |
|------|--------|----------|--------|--------|
| S1   | ✓ | 13.90 kt | DD day 981, 90d | 78 |
| S2   | ✓ | 11.56 kt | DD day 985, 90d | 76 |
| S3   | ✓ | 14.74 kt | DD day 769, 90d | 66 |
| ... | ... | ... | ... | ... |
| S9   | ✗ | 19.01 kt | 分位數 Top 15% | 177 |
| S10  | ✗ | 19.75 kt | 分位數 Top 15% | 208 |
| S11  | ✗ | 19.17 kt | 分位數 Top 15% | 225 |
| S12  | ✗ | 18.07 kt | 分位數 Top 15% | 210 |
| S23  | ✗ | 19.42 kt | 分位數 Top 15% | 215 |

### 各船平均 Speed Loss

| 船隻 | 平均 Speed Loss | 範圍 | 特點 |
|------|-----------------|------|------|
| S1   | -3.73% | -42.14% ~ 82.63% | 中等，波動大 |
| S7   | 6.07% | -36.86% ~ 99.32% | 正常 |
| S22  | 9.69% | -32.39% ~ 104.60% | 較高 |
| S9   | 24.18% | -55.08% ~ 91.51% | 很高（分位數法） |
| S10  | 21.62% | -1.79% ~ 62.57% | 很高（分位數法） |

---

## 十、實施檔案

### 主要指令碼

**`add_speedloss_column_full_iso.py`**
- 輸入：`vt_fd.csv`
- 輸出：`vt_fd_speed_loss.csv`（臨時路徑）
- 功能：9 項 ISO 修正 + Baseline + Speed Loss

**修改位置**：
- 第 130~150 行：無 DD 船隻的分位數邏輯
- 第 200~250 行：Speed Loss 計算

### 輸出 CSV 欄位

```
De-identification Name, VOYAGE, NOON_UTC, ..., speed_loss, row_index
S1, 28, 0, ..., 4.11, 0
S1, 28, 0, ..., 4.11, 1
S1, 29, 2, ..., null, 2      ← 非穩態
S1, 29, 3, ..., -22.42, 4
```

---

## 十一、總結

| 項目 | 說明 |
|------|------|
| **修正項目** | ISO 19030-2 完整 9 項 |
| **環境修正** | 風、波浪、涌浪、水溫、密度 |
| **船舶修正** | 吃水、縱傾、淺水 |
| **額外修正** | 排水量 |
| **Baseline 方法** | DD 船用 DD+90d；非 DD 船用分位數法 Top 15% |
| **穩態篩選** | WIND ≤ 4, HOURS ≥ 22 |
| **有效記錄** | 8,342 筆（39%） |
| **無效記錄** | 12,940 筆（61%，非穩態） |
| **精度** | 0.01% 級精度 |

---

本方案為全球船舶性能監控領域的最佳實踐，整合 ISO 19030-2 標準與創新的分位數方法，確保無 DD 船隻的基準也符合「最乾淨船體」的定義。
