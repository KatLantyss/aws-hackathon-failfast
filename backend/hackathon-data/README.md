# Hackathon 資料集說明

## 任務

基於航行日報（`vt_fd.csv`）與水下養護事件（`maintenance.csv`），分析船殼汙損與螺旋槳粗糙度對船舶推進效能的影響。本題目包含兩項產出：

1. **預測模型** — 建立通用數學模型，推論預測船在指定日期、給定航行/環境條件下的**主機全速油耗**。預測標的日只使用單一燃料，例如當日使用 HSHFO 時，即預測 `ME_FULLSPEED_CONSUMP_HSHFO`；每個 `PREDICT` 儲存格皆對應到要預測的燃料類別。該油耗會受到環境、船體等因素影響，需由參賽者透過模型分析以完成推論。
2. **Speed Loss Dashboard** — 於 ISO 19030 框架下計算並視覺化 Speed Loss，呈現推進效能隨時間的變化趨勢、船殼汙損歸因、以及與養護事件的時序對應。

> 本文件說明資料集與預測任務。評分方式與配分請見大會說明會簡報。

---

## 檔案

| 檔案                | 說明                                   |
| ----------------- | ------------------------------------ |
| `vt_fd.csv`       | 15 艘船 × 5 年的航行日報（僅排除純靠港/錨泊日；保留各種全速時數與天候的航行日，供 Speed Loss 繪製連續日程） |
| `maintenance.csv` | 船舶養護紀錄                               |
| `README.md`       | 本文件                                  |

---

## 船舶編號

- **S1–S12**：訓練船（所有數據完整公開）
- **S21–S23**：預測船（特定區間的效率與油耗數據被遮蔽）

船型分組：
- S1–S8, S21 為同型船（W1 型）
- S9–S12, S22–S23 為同型船（W2 型）

W1 與 W2 為相同設計的姊妹船，營運於不同航線。

---

## vt_fd.csv 欄位說明

### 欄位分類

|      類別       | 遮蔽區間內 | 欄位                                                                                                                                                                                                   |
| :-----------: | :---: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A** (環境/航行) |  可見   | De-identification Name, VOYAGE, NOON_UTC, AVG_SPEED, SPEED_THROUGH_WATER, ME_AVG_RPM, PROPELLER_SPEED, FORE_DRAFT, AFTER_DRAFT, MID_DRAFT, DISPLACEMENT, CARGO_ON_BOARD, WIND_SCALE, WIND_SPEED, WIND_DIRECTION, SEA_HEIGHT, SEA_DIRECTION, SWELL_HEIGHT, SWELL_DIRECTION, SEA_WATER_TEMP, WATER_DEPTH, TOTAL_DISTANCE, SEA_SPEED_DISTANCE, DIFF_STW_SOG_SLIP, FULL_SPD_STW_SLIP |
| **H** (主機性能)  |  隱藏   | HORSE_POWER, LOAD_PCT, SFOC, ME_SLIP, THRUST, THRUST_QUOTIENT                                                                                                                                        |
|  **T** (油耗)   | 隱藏/預測 | TOTAL_CONSUMP, ME_FULLSPEED_CONSUMP_HSHFO/VLSFO/ULSFO/LSMGO/BIO_HSFO, ME_CONSUMPTION                                                                                                                 |
| **F** (預測日篩選/建模輔助)  |  可見   | WIND_SCALE（風速）, HOURS_FULL_SPEED（全速航行時數）— 用於界定預測日條件，亦可作為建模特徵/加權                                                                                                        |

### 欄位詳細

| 欄位                            | 說明                   | 單位       |
| ----------------------------- | -------------------- | -------- |
| De-identification Name        | 船舶代號                 | S1–S23   |
| VOYAGE                        | 航次編號                 | —        |
| NOON_UTC                      | 相對天數（Day 0 = 該船最早紀錄） | days     |
| AVG_SPEED                     | 平均對地航速（SOG）          | knots    |
| SPEED_THROUGH_WATER           | 對水航速（STW）            | knots    |
| ME_AVG_RPM                    | 主機平均轉速               | RPM      |
| PROPELLER_SPEED               | 螺旋槳轉速                | RPM      |
| FORE_DRAFT / AFTER_DRAFT      | 首/尾吃水                | m        |
| DISPLACEMENT                  | 排水量                  | MT       |
| CARGO_ON_BOARD                | 載貨量                  | MT       |
| WIND_SCALE                    | 風力等級                 | Beaufort |
| SEA_HEIGHT                    | 浪高                   | m        |
| SEA_WATER_TEMP                | 海水溫度                 | °C       |
| WIND_SPEED                    | 風速                   | knots    |
| WIND_DIRECTION                | 風向（相對/羅經）           | deg/點   |
| SWELL_HEIGHT                  | 湧浪高度                 | m        |
| SWELL_DIRECTION               | 湧浪方向                 | deg/點   |
| SEA_DIRECTION                 | 浪方向                  | deg/點   |
| WATER_DEPTH                   | 水深（淺水效應判定）          | m        |
| MID_DRAFT                     | 舯吃水                  | m        |
| TOTAL_DISTANCE                | 當日對地總航距             | nm       |
| SEA_SPEED_DISTANCE            | 全速時段對水航距            | nm       |
| DIFF_STW_SOG_SLIP             | 對水-對地速差（洋流代理）      | knots/%  |
| FULL_SPD_STW_SLIP             | 全速時段對水滑差            | %        |
| HORSE_POWER                   | 主機功率                 | kW       |
| LOAD_PCT                      | 主機負載                 | %MCR     |
| SFOC                          | 比油耗 (單位馬力耗油率)    | g/kWh    |
| ME_SLIP                       | 主機/螺旋槳滑差             | %        |
| THRUST                        | 推力                   | kN       |
| THRUST_QUOTIENT               | 推力係數                 | —        |
| TOTAL_CONSUMP                 | 當日總油耗（含輔機/鍋爐）        | MT/day   |
| ME_FULLSPEED_CONSUMP_HSHFO    | 主機全速油耗（高硫重油）         | MT/day   |
| ME_FULLSPEED_CONSUMP_VLSFO    | 主機全速油耗（極低硫燃油）        | MT/day   |
| ME_FULLSPEED_CONSUMP_ULSFO    | 主機全速油耗（超低硫燃油）        | MT/day   |
| ME_FULLSPEED_CONSUMP_LSMGO    | 主機全速油耗（低硫輕柴油）        | MT/day   |
| ME_FULLSPEED_CONSUMP_BIO_HSFO | 主機全速油耗（生質高硫重油）       | MT/day   |
| ME_CONSUMPTION                | 主機油耗合計               | MT/day   |
| HOURS_FULL_SPEED              | 全速航行時數               | hr       |
| HOURS_TOTAL                   | 總航行時數                | hr       |

> **關於 Speed Loss 與航速欄位**：`SPEED_THROUGH_WATER`（STW，對水航速）與 `AVG_SPEED`（SOG，對地航速）為兩個獨立來源的欄位。兩者填充率皆 100%，但因洋流/潮流影響，同日可能有明顯差異。建模時請留意各欄位的物理意義與適用情境。

---

## 燃料熱值對照

不同油品熱值各異，跨燃料比較或折算為統一當量時，可採用下列參考基準。油料名稱與 `ME_FULLSPEED_CONSUMP_*` 欄位的命名一致，避免混淆。

| 燃料欄位 | 油品全稱 | 熱值 (MJ/kg) |
|------|------|:----:|
| ME_FULLSPEED_CONSUMP_HSHFO | High Sulphur Heavy Fuel Oil（高硫重油）| 40.2 |
| ME_FULLSPEED_CONSUMP_ULSFO | Ultra Low Sulphur Fuel Oil（超低硫燃油）| 41.2 |
| ME_FULLSPEED_CONSUMP_VLSFO | Very Low Sulphur Fuel Oil（極低硫燃油）| 40.2 |
| ME_FULLSPEED_CONSUMP_LSMGO | Low Sulphur Marine Gas Oil（低硫輕柴油）| 42.7 |
| ME_FULLSPEED_CONSUMP_BIO_HSFO | Bio Blended High Sulphur Fuel Oil（生質高硫重油）| 39.4 * |

> 當日若使用多種燃料，參賽者應自行折算為統一當量。

> **關於生質燃料（BIO_HSFO）**：生質能源是航運減碳的未來趨勢，本資料集亦已涵蓋。惟生質燃料因摻配比例不同，熱值可能有所波動（表中 39.4 MJ/kg 為近似值，標註 *），跨燃料折算時的不確定性較高。在本次資料集中，BIO_HSFO 於訓練窗口的使用有限，而預測窗口則完全未使用；因此預測標的不受其熱值影響。

---

## Placeholder 說明

預測船（S21–S23）在養護後一段期間的數據被遮蔽：

| 標記 | 意義 |
|:----:|------|
| `HIDDEN` | 資料存在但不提供（H 類欄位 + 非預測燃料的 T 類欄位）|
| `PREDICT` | **需要預測的值**（當日使用的燃料之 ME_FULLSPEED_CONSUMP_* 欄位）|
| (空值) | 原始即為缺失 |

每個 `PREDICT` 標記對應一個預測項目。全部共 **102 個 PREDICT**（14 個事件，每事件 5–10 天）。

> **關於資料集與預測日**：`vt_fd.csv` 保留各種全速時數與天候的航行日（僅排除純靠港/錨泊日，即全速航行時數為 0 者），以保留連續日程供繪製 Speed Loss 趨勢。惟所有被要求預測的日子（`PREDICT`）皆已篩選為滿足下列條件的乾淨穩態點：**1) 全速航行 ≥22 小時、2) 風速 ≤4 級（Beaufort）、3) 當日僅使用單一燃料**。建模時可自行運用 `HOURS_FULL_SPEED`、`WIND_SCALE` 等欄位篩選或加權訓練資料。

---

## maintenance.csv 欄位

| 欄位 | 說明 |
|------|------|
| ship_id | 船舶代號 (S1–S23) |
| event_type | 養護類型：PP / UWI+PP / UWC / UWC+PP / DD / UWI |
| event_date | 養護日期 (YYYY-MM-DD) |
| propeller_condition | 螺旋槳狀態 (Good/Fair/Poor) |
| hull_fouling_type | 船殼汙損類型 (barnacle/slime/algae/tubeworm/calcium) |
| hull_coating_condition | 塗層狀態 (Good/Fair/Poor) |
| cavitation_found | 是否發現空蝕 (Yes/No) |
| draft_fwd_m | 檢查時首吃水 (m) |
| draft_aft_m | 檢查時尾吃水 (m) |

### 養護類型說明

| 類型 | 全稱 | 物理介入 |
|:----:|------|----------|
| PP | Propeller Polishing | 螺旋槳拋光 |
| UWI+PP | Inspection + Polishing | 水下檢查 + 螺旋槳拋光 |
| UWC | Underwater Cleaning | 船殼清洗 |
| UWC+PP | Cleaning + Polishing | 船殼清洗 + 螺旋槳拋光 |
| DD | Dry Dock | 進塢（全面塗裝 + 機械保養）|
| UWI | Underwater Inspection | 水下檢查（僅拍照，無物理介入）|

---

## 提交格式（預測模型）

提交 CSV 檔案，包含以下欄位：

```csv
ship_id,day,fuel_type,predicted_value
S21,450,ME_FULLSPEED_CONSUMP_HSHFO,85.3
S21,451,ME_FULLSPEED_CONSUMP_HSHFO,84.7
...
```

- `ship_id`: 預測船代號
- `day`: NOON_UTC 相對天數
- `fuel_type`: 該 `PREDICT` 儲存格對應的燃料欄位名稱（即當日實際使用的燃料）
- `predicted_value`: 預測的該燃料全速油耗（MT/day）

對應 `vt_fd.csv` 中每個標記為 `PREDICT` 的儲存格，共 102 項。

> 注意: 由於船隻每日全速航行的時長可能有異，數學模型應執行校正；預測標的與 csv 其他列相同，是在全速時段內消耗的油料總量。

---

## 參賽者自由度

預測標的明確，但通往預測的路徑完全開放：建模方法自選（物理模型、統計回歸、ML/DL、hybrid）、特徵工程自訂、可使用公開外部資料（海水溫度、洋流等）、校正策略自選。


