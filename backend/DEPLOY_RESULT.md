API 清單
Base URL: https://4rh4qj5e3i.execute-api.us-east-1.amazonaws.com/dev
 
1. Health Check
 
GET /health
確認 API 和 DynamoDB 連線狀態。
 
2. 船舶列表
 
GET /api/v1/vessels
回傳全部 15 艘船（S1–S12 訓練船、S21–S23 預測船）。
 
3. 船舶概況
 
GET /api/v1/vessels/{vessel_id}
單艘船的統計摘要：總筆數、平均速度、平均燃耗、航次範圍。
 
4. 航行日報
 
GET /api/v1/vessels/{vessel_id}/noon-reports
逐筆每日正午報告。
 
Query Param	說明	預設
limit	最大筆數	100
voyage	篩選單一航次	全部
5. Speed Loss 分析
 
GET /api/v1/vessels/{vessel_id}/speed-loss
計算推進效能隨時間的變化趨勢。
 
目前做法（待改進）：
 
Reference speed = 以 calm condition（風力 ≤ 3, 浪高 ≤ 1m）的 STW 取中位數
speed_loss = ref_speed - actual_STW
應改成（基於題目資料）：
 
直接用 FULL_SPD_STW_SLIP（全速對水滑差 %）—— 這個欄位已是題目算好的推進效率指標，數值越高代表效能越差
6. Speed Loss 歸因分析
 
GET /api/v1/vessels/{vessel_id}/speed-loss-attribution
將 Speed Loss 拆分為四個來源：hull fouling、weather、propeller、other。
 
目前做法（heuristic，不精確）：
 
hull_loss = 距上次 DD 天數 × 0.0005
weather_loss = 風力 × 0.04 + 浪高 × 0.08
propeller_loss = ME_SLIP × 0.02
應改成（基於資料）：
 
UWC 事件前後 FULL_SPD_STW_SLIP 的差 → hull fouling 貢獻
PP 事件前後 FULL_SPD_STW_SLIP 的差 → propeller 貢獻
DIFF_STW_SOG_SLIP → 洋流/weather 影響（跟 hull fouling 無關）
7. 維護事件紀錄
 
GET /api/v1/vessels/{vessel_id}/maintenance-events
該船全部養護事件，依時間排序。含類型（DD/UWC/PP/UWI+PP/UWC+PP/UWI）、船殼污損類型、螺旋槳狀態。
 
8. 維護建議
 
GET /api/v1/vessels/{vessel_id}/maintenance-recommendation
根據近 90 天 ME_SLIP 趨勢和距上次維護天數，建議 URGENT / ROUTINE，以及建議類型（DD / UWC）。
 
9. 船隊排名
 
GET /api/v1/fleet/ranking
S1–S12 訓練船依 avg speed loss 排名。也回傳 avg ME slip、avg 燃耗。
 
10. 燃油消耗預測
 
POST /api/v1/predict/fuel-consumption
給定航行條件，預測 ME 燃油消耗，並計算反事實分析（降速 1 kn 可省多少油）。
 
Request Body:
 
json
 
{
  "vessel_id": "S1",
  "speed_kn": 15.0,
  "draft_fwd": 14.0,
  "draft_aft": 14.5,
  "cargo_on_board": 85000,
  "wind_scale": 3,
  "sea_height": 1.0
}
目前模型： consumption ≈ a × speed³（cubic speed LSQ fit）
 
題目要求的模型： 需能預測 ME_FULLSPEED_CONSUMP_{HSHFO/VLSFO/ULSFO/LSMGO/BIO_HSFO}（依當日燃料類型），且要能做 UWC/PP 反事實推論。