# 本地開發環境啟動指南

## 🚀 快速開始（一鍵啟動）

### Windows PowerShell（推薦）

#### 1. 啟動後端 API
```powershell
# 終端 1：後端
cd backend-api
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

#### 2. 啟動前端應用
```powershell
# 終端 2：前端
cd frontend
npm install
npm run dev
```

#### 3. 運行 Speed Loss 計算（可選）
```powershell
# 終端 3：計算
cd yangming-aws-summit-hackathon
python speed_loss_pipeline.py
```

---

## 📍 訪問應用

| 服務 | 地址 | 說明 |
|------|------|------|
| 前端應用 | `http://localhost:5173` | Vue 3 開發服務器 |
| 後端 API | `http://localhost:8000` | FastAPI 服務 |
| API 文檔 | `http://localhost:8000/docs` | Swagger UI |

---

## 🔗 Speed Loss 分析入口

### 直接訪問
```
http://localhost:5173/speed-loss-analysis
```

### 或在導航菜單中選擇
- 頂部導航 → Speed Loss Analysis

---

## 📊 可用 API 端點

### 1. 獲取可視化數據
```bash
curl http://localhost:8000/api/speed-loss/visualization-data
```

### 2. 獲取船隊統計
```bash
curl http://localhost:8000/api/speed-loss/fleet-statistics
```

### 3. 獲取異常事件
```bash
curl http://localhost:8000/api/speed-loss/anomalies
```

### 4. 觸發計算（可選）
```bash
curl -X POST http://localhost:8000/api/speed-loss/calculate
```

---

## ⚙️ 環境要求

- **Python 3.10+**
- **Node.js 18+**
- **npm 9+**

### 驗證環境
```powershell
python --version    # Python 3.10+
node --version      # Node.js 18+
npm --version       # npm 9+
```

---

## 📦 依賴安裝

### 後端依賴
```powershell
cd backend-api
pip install -r requirements.txt
```

### 前端依賴
```powershell
cd frontend
npm install
```

---

## 🔧 自定義配置

### 後端 API 地址
編輯 `frontend/src/views/SpeedLossAnalysis.vue`：
```typescript
// 修改 fetch URL
const response = await fetch('http://localhost:8000/api/speed-loss/visualization-data')
```

### 前端端口
編輯 `frontend/vite.config.ts`：
```typescript
export default defineConfig({
  server: {
    port: 5173  // 修改此處
  }
})
```

### 後端端口
修改啟動命令：
```powershell
uvicorn app:app --reload --host 0.0.0.0 --port 8001  # 修改 --port
```

---

## 🐛 故障排除

### 前端無法連接後端
1. 確認後端正在運行：`http://localhost:8000/health`
2. 檢查防火牆設置
3. 查看瀏覽器控制台的 CORS 錯誤

### Speed Loss 數據未顯示
1. 運行 `python speed_loss_pipeline.py` 生成數據
2. 檢查 `yangming-aws-summit-hackathon/speed_loss_output/` 目錄
3. 重新啟動後端服務

### npm 依賴錯誤
```powershell
cd frontend
rm -r node_modules package-lock.json
npm install
```

---

## 📱 完整工作流

### 第一次使用
```powershell
# 1. 計算 Speed Loss 數據
cd yangming-aws-summit-hackathon
python speed_loss_pipeline.py

# 2. 安裝後端依賴
cd ../backend-api
pip install -r requirements.txt

# 3. 安裝前端依賴
cd ../frontend
npm install

# 4. 啟動後端（終端 1）
cd ../backend-api
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# 5. 啟動前端（終端 2）
cd ../frontend
npm run dev

# 6. 訪問應用
# 瀏覽器打開：http://localhost:5173/speed-loss-analysis
```

---

## 📊 測試 Speed Loss 功能

1. **訪問儀表板**
   ```
   http://localhost:5173/speed-loss-analysis
   ```

2. **檢查 KPI 卡片**
   - 船隊平均 Speed Loss
   - 最佳表現船舶
   - 需關注船舶
   - 異常事件計數

3. **互動功能**
   - 選擇單艘船舶
   - 調整時間窗口
   - 查看異常詳情
   - 懸停查看提示

---

## 🚀 生產部署

### Docker 方式
```powershell
# 構建鏡像
docker-compose build

# 運行容器
docker-compose up -d
```

### AWS 部署
```powershell
# 後端：AWS Lambda + API Gateway
# 前端：AWS S3 + CloudFront

# 詳見 Deploy.md
```

---

## 📞 常見問題

**Q: 後端啟動報錯 `ModuleNotFoundError`？**  
A: 運行 `pip install -r requirements.txt`

**Q: 前端無法載入 Speed Loss 數據？**  
A: 確認已運行 `speed_loss_pipeline.py` 生成數據文件

**Q: 如何修改計算邏輯？**  
A: 編輯 `yangming-aws-summit-hackathon/speed_loss_pipeline.py`，重新運行

**Q: 如何添加新的可視化圖表？**  
A: 編輯 `frontend/src/components/SpeedLossDashboard.vue`

---

## ✅ 驗證清單

- [ ] Python 3.10+ 已安裝
- [ ] Node.js 18+ 已安裝
- [ ] 後端依賴已安裝
- [ ] 前端依賴已安裝
- [ ] Speed Loss 數據已生成
- [ ] 後端服務正在運行 (port 8000)
- [ ] 前端開發服務器正在運行 (port 5173)
- [ ] 可訪問 http://localhost:5173/speed-loss-analysis

---

**準備好了？開始探索 Speed Loss 儀表板吧！** 🚢 📊
