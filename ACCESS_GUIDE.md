# 🚀 Speed Loss 分析系統 - 本地訪問指南

## ✅ 已啟動的服務

### 前端應用
- **地址：** http://localhost:5173
- **技術：** Vue 3 + Vite + Tailwind CSS
- **狀態：** ✅ 運行中

### 後端 API
- **地址：** http://localhost:8000
- **技術：** FastAPI + Uvicorn
- **API 文檔：** http://localhost:8000/docs (Swagger UI)
- **狀態：** ✅ 運行中

---

## 🎯 立即訪問

### 方式 1：打開 Speed Loss 儀表板（推薦）
```
http://localhost:5173/speed-loss-analysis
```

### 方式 2：訪問主應用首頁
```
http://localhost:5173
```
然後從菜單中選擇 **"Speed Loss Analysis"**

### 方式 3：API 文檔
```
http://localhost:8000/docs
```

---

## 📊 Speed Loss 儀表板功能

### KPI 卡片
- ✓ 船隊平均效能損失
- ✓ 最佳表現船舶
- ✓ 需關注船舶
- ✓ 異常事件計數

### 互動圖表
- ✓ 時間序列趨勢（可切換 L1/L2 分析）
- ✓ 維修效益時間軸
- ✓ 異常告警表格
- ✓ 效能對比熱力圖

### 控制選項
- ✓ 按船舶篩選
- ✓ 時間窗口選擇（30天/90天/6月/1年/全部）
- ✓ 異常調查功能
- ✓ 報告生成和數據匯出

---

## 🔌 可用 API 端點

### 獲取可視化數據
```bash
GET http://localhost:8000/api/speed-loss/visualization-data

# 返回格式：
{
  "fleet_summary": { ... },
  "timeseries": { ... },
  "maintenance_events": [ ... ]
}
```

### 獲取船隊統計
```bash
GET http://localhost:8000/api/speed-loss/fleet-statistics

# 返回 15 艘船的統計數據
```

### 獲取異常事件
```bash
GET http://localhost:8000/api/speed-loss/anomalies

# 返回前 100 個異常事件
```

### 觸發計算（可選）
```bash
POST http://localhost:8000/api/speed-loss/calculate

# 在後台運行 speed_loss_pipeline.py
```

---

## 📈 數據狀態

### 當前數據
- **船隊平均 Speed Loss：** 102.3%
- **船舶數量：** 15 艘
- **分析期間：** Day 0 - Day 1825（5 年）
- **異常事件：** 12,894 次
- **最近更新：** 2026-07-15

### 數據位置
```
yangming-aws-summit-hackathon/speed_loss_output/
├── speed_loss_complete.csv          # 完整計算數據
├── fleet_statistics.csv             # 船隊統計
├── anomalies.csv                    # 異常事件
└── visualization_data.json          # 前端數據
```

---

## 🔄 工作流程

### 1. 查看儀表板
```
瀏覽器 → http://localhost:5173/speed-loss-analysis
```

### 2. 探索數據
- 查看 KPI 卡片了解船隊概況
- 選擇單艘船舶查看詳細趨勢
- 調整時間窗口進行時期對比

### 3. 深入分析
- 點擊異常事件查看詳情
- 懸停時間軸了解維修效益
- 查看熱力圖進行船隊對比

### 4. 導出結果
- 點擊"生成報告"創建 HTML 報告
- 點擊"匯出數據"下載 CSV 文件

---

## 🛠️ 常用命令

### 重新計算 Speed Loss
```powershell
cd yangming-aws-summit-hackathon
python speed_loss_pipeline.py
```

### 查看後端日誌
```powershell
# 後端服務的終端輸出
```

### 查看前端編譯信息
```powershell
# 前端服務的終端輸出
```

### 停止服務
```powershell
# 按 Ctrl+C 停止終端中的服務
```

---

## 🐛 常見問題

### Q: Speed Loss 數據為空？
**A:** 
1. 確認已運行 `python speed_loss_pipeline.py`
2. 檢查 `yangming-aws-summit-hackathon/speed_loss_output/` 目錄
3. 重新啟動後端服務

### Q: 後端返回 404 錯誤？
**A:**
1. 確認後端服務正在運行（端口 8000）
2. 檢查防火牆設置
3. 查看瀏覽器控制台的 CORS 錯誤

### Q: 儀表板圖表不顯示？
**A:**
1. 打開瀏覽器開發者工具（F12）
2. 查看 Network 和 Console 標籤
3. 確認 API 調用成功

### Q: 如何修改告警閾值？
**A:**
編輯 `yangming-aws-summit-hackathon/speed_loss_pipeline.py`：
```python
ANOMALY_THRESHOLD_L1 = 20  # 修改此值（%）
```

---

## 📞 技術支持

### 查看 API 文檔
訪問 Swagger UI：
```
http://localhost:8000/docs
```

### 檢查後端健康狀態
```bash
curl http://localhost:8000/health
```

### 查看詳細日誌
後端和前端的終端輸出包含詳細的調試信息

---

## 🎉 現在享受 Speed Loss 分析！

您已經準備好使用完整的 Speed Loss 分析系統了。以下是推薦的探索路徑：

1. **第一步（2 分鐘）**
   - 訪問 http://localhost:5173/speed-loss-analysis
   - 查看 KPI 卡片和整體概況

2. **第二步（5 分鐘）**
   - 選擇不同的船舶
   - 觀察時間序列趨勢
   - 比較 L1 和 L2 的分析方法

3. **第三步（10 分鐘）**
   - 查看異常事件詳情
   - 分析維修效益
   - 查看船隊對比熱力圖

4. **進階（20 分鐘）**
   - 瀏覽 API 文檔
   - 查看完整的計算數據（CSV）
   - 理解三層計算方法

---

**祝你的分析之旅愉快！** 🚢 ⚓ 📊

有任何問題，請查看 START_DEV.md 或 SPEED_LOSS_IMPLEMENTATION_GUIDE.md
