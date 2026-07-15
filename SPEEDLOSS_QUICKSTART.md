# Speed Loss Dashboard — 快速開始

## 🚀 一句話：
**基於 ISO 19030 的 STW 百分位基線法，實時監控 15 艘船隊的推進效能衰退，支持維修效益跟蹤。**

---

## 📊 儀表板亮點

### KPI 卡片
- **船隊平均效能損失**：5.11%（目標控制 < 10%）
- **最佳表現**：S5 (4.54%)
- **需關注**：S8 (6.33%)
- **異常事件**：77 個維修記錄

### 交互功能
- ✅ 時間序列圖（Speed Loss 趨勢）
- ✅ 維修時間線（標記 DD/UWC/UWI+PP）
- ✅ 異常告警表（高速損失、異常油耗）
- ✅ 熱力圖（船隊快速定位）

---

## 🎯 數據指標解讀

### Speed Loss % 的含義
```
Speed Loss = (Expected STW - Actual STW) / Expected STW × 100

示例：
  Expected STW = 18.5 knots
  Actual STW   = 17.8 knots
  Speed Loss   = (18.5 - 17.8) / 18.5 × 100 = 3.8%
```

### 為什麼用 STW？
- ✅ **物理意義明確**：只受船體阻力影響
- ✅ **排除環保擾動**：已篩選平靜條件（風力 ≤ 4，全速小時 ≥ 22）
- ✅ **無 FOC 複雜性**：避免燃料類型、熱值換算的干擾
- ✅ **ISO 19030 合規**：相對基準法的標準實現

---

## 📈 維修效益對標

| 維修類型 | 平均改善 | 示例 |
|---------|---------|------|
| **DD（進塢）** | 20%+ | S2 Day 985: 28.5% → 4.9% |
| **UWC（水下清洗）** | 8-15% | S4 Day 147: 4.8% → 7.0% → 重新平衡 |
| **UWI+PP（檢查+拋光）** | 3-5% | S4 Day 1249: 6.8% → 3.9% |

---

## 🔧 訪問方式

### 本地開發
```bash
# 進入前端目錄
cd ym-hackthon/frontend

# 確保伺服器運行（通常已自動啟動）
npm run dev

# 瀏覽器訪問
http://localhost:5173/speed-loss-analysis
```

### 生產環境
待 CloudFront 部署完成後，通過以下方式訪問：
```
https://ship-analysis.example.com/speed-loss-analysis
```

---

## 📁 相關文件速查

| 用途 | 文件 | 說明 |
|------|------|------|
| **計算邏輯** | `handler.py` | `get_sl_by_percentile()` 函數 |
| **前端頁面** | `SpeedLossAnalysis.vue` | 數據加載容器 |
| **儀表板組件** | `SpeedLossDashboard.vue` | UI 實現 |
| **路由配置** | `router/index.ts` | 註冊 `/speed-loss-analysis` |
| **數據源** | `visualization_data.json` | 15 艘船 × 日均線 |
| **統計 CSV** | `speed_loss_summary.csv` | 船舶平均、P10/P90 等 |
| **維修對比** | `speed_loss_maintenance_impact.csv` | 事件前後 30 天對比 |

---

## ❓ 常見問題

### Q: Speed Loss 為什麼會是負值？
**A**: 物理上合理。可能原因：
- 順流或有利海況
- RPM 切換到不同運行範圍
- 基線百分位的自然變異
- **不超過 10%** 是正常的

### Q: 為什麼某些維修後 Speed Loss 還在升高？
**A**: 通常是因為：
- 維修後 RPM 分布改變（低 RPM 效率較差）
- 統計樣本不足（< 5 天數據）
- 立即進入高風況海域
- **檢查 FOC 下降 %** 更準確

### Q: 如何更新最新的數據？
**A**: 
1. 後端運行計算：`python _export_sl_csv.py`
2. 轉換為 JSON：`python csv_to_json.py`
3. 自動同步到前端 `public/data/`
4. 刷新瀏覽器即可看到最新數據

### Q: 能否比較不同時間段的性能？
**A**: 可以。Dashboard 支援時間窗口選擇（暫時顯示完整數據），未來會加入 30/90/180 天對比。

---

## 📞 技術聯繫

- **計算問題**：查看 `handler.py` 中的 `get_sl_by_percentile()` 和 `get_baseline_ref_stw()`
- **前端顯示**：檢查 `SpeedLossDashboard.vue` 的計算屬性和插值
- **數據源**：查詢 `speed_loss_timeline.csv` 的原始值

---

## ✅ 已驗證項目
- [x] 15 艘船 × 5 年數據計算完成
- [x] Speed Loss 分佈符合預期（4.5-6.3%）
- [x] 維修效益可量化追蹤
- [x] 本地 JSON 加載無誤
- [x] 儀表板頁面可訪問
- [x] KPI 卡片動態綁定

---

**最後更新**: 2026-07-15 | **狀態**: ✅ Ready to Deploy
