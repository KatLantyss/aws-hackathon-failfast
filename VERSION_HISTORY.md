# Speed Loss 計算方法版本歷史

## 版本 1.0：Power Coefficient 法（失敗）❌

**時間**: 2026-07-15 初版

**方法**:
```
Power Coefficient = FOC / RPM³
Speed Loss = 不同時期的 PC 比較
```

**問題**:
- FOC ↓ 下降，但 Speed Loss ↑ 上升（方向矛盾）
- 負值率 70%（意味著維修後「反而更好」？不合理）
- RPM³ 在低轉速時效率差，導致系統性偏差

**成效**: ⭐ 不可靠

**結論**: 放棄 FOC-based，改用 STW-based

---

## 版本 2.0：STW-based 相對基準法（部分成功）⚠️

**時間**: 2026-07-15 後期

**方法**:
```
Baseline STW = 全歷史 (2021-2025) 的 90th percentile STW at each RPM
Speed Loss = (Baseline - Actual STW) / Baseline × 100
```

**特性**:
- ISO 19030 Layer 1 合規
- RPM 正規化 FOC 改善指標加入
- 前端有「維修效益分析表」

**結果**: 
- 負值率: 8-10%（改善）
- 但維修前後沒有明顯的 SL 下降
- 原因: Baseline 是「5 年前的最佳狀態」，現實達不到

**成效**: ⭐⭐ 理論上合理，實踐上誤導

**用戶反饋**: 「維修後 Speed Loss 反而提升，這不合理」

**結論**: Baseline 定義錯誤，需要改為「進塚後清潔狀態」

---

## 版本 3.0：進塚後基線法（當前）🔄

**時間**: 2026-07-15 下午

**方法**:
```
Baseline STW = 進塚後 7-14 天的 90th percentile STW at each RPM
Speed Loss = (Baseline_clean - Actual STW) / Baseline_clean × 100

特性:
- Per-cycle baseline（每個維修週期獨立基線）
- 維修日期後 7-14 天作為「清潔狀態參考」
- 後續衰退 = 真實汙損程度
```

**預期成效**:
- 維修後 SL 應明顯下降
- 改善率應 > 50%

**實際驗證**:
- CSV 數據: 改善率 53.8% (7/13 維修事件改善)
- **前端顯示**: ❓ 用戶反饋「不是這樣」 — **需驗證**

**待解決**:
- [ ] 檢查前端實際顯示的 Speed Loss 序列
- [ ] 逐個維修事件對應 speed loss 變化
- [ ] 確認 baseline 計算是否正確應用到時間線

**狀態**: 🔄 需要前端驗證

---

## 嘗試過但未採用的方法

### A. Polynomial Baseline (Layer 2)
- 使用二次多項式擬合 RPM→STW
- 問題: RPM 分布改變時失效
- 棄用原因: 不夠穩定

### B. 全週期前 30% 作 Baseline
- 只用 cycle 0 前 30% 的數據
- 問題: 仍有 60% 負值
- 棄用原因: 無效

### C. 相同 RPM 帶下的改善 (RPM 正規化)
- ✅ 仍保留，作為輔助指標
- 幫助理解「同轉速下的改善」

---

## 關鍵發現

### Issue 1: Baseline 選擇的物理意義
```
錯誤: Baseline = max(history)
     → 虛幻的「理想狀態」

正確: Baseline = post-maintenance average
     → 實際達到的「清潔狀態」

差異: 前者導致負值，後者導致正向下降
```

### Issue 2: RPM 分布的影響
```
維修前: 可能低速 (RPM 40)
       Low RPM 本身效率低
       
維修後: 可能高速 (RPM 75)
       High RPM 效率高
       
結果: 相同 RPM 下改善有限
      但整體能力提升（可跑高速）
```

### Issue 3: 數據可用性
```
77 個維修事件
↓
31 個有前後 30 天數據
↓
13 個有完整 speed loss 數據
↓
真實可驗證的改善: 53.8% (7/13)
```

---

## 下一步驗證清單

- [ ] 逐個維修事件列出 Speed Loss 時間序列
- [ ] 檢查前端展示的數據是否與 CSV 一致
- [ ] 確認是否所有維修事件都正確應用了新 baseline
- [ ] 可能需要調整 baseline 的計算方式或時間窗口

---

**最後更新**: 2026-07-15  
**負責人**: Speed Loss 診斷  
**當前狀態**: ⚠️ 需要用戶驗證前端實際顯示
