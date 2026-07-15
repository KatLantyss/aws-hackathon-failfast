/**
 * 異常檢測模型 v3.0 - 船體能效監控專用
 *
 * 項目背景：
 * • 著重船體能效（影響 Speed Loss 達 20%+）
 * • 不關注主機效能（SFOC - 隱藏數據）
 * • 目標：及時發現需要清潔的船舶，通過維修恢復能效
 *
 * 統計基礎：74 個維護事件分析
 * • 成功維修（改善）：41 個 (55.4%)
 * • 失敗維修（無改善/惡化）：33 個 (44.6%)
 * • 合理異常率：44.6%
 */

export interface MaintenanceEvent {
  type: string
  delta: number | null
  is_uwi_only?: boolean
  day?: number
  before?: number
  after?: number
}

export function detectAnomaly(
  event: MaintenanceEvent
): {
  isAnomalous: boolean
  reason?: string
  severity?: 'CRITICAL' | 'WARNING'
  icon?: string
} {
  if (!event || event.delta === null) {
    return { isAnomalous: false }
  }

  // 純 UWI（水下檢查）：不應改善
  if (event.is_uwi_only) {
    if (event.delta < -1.0) {
      return {
        isAnomalous: true,
        reason: `🔴 異常：純檢查卻有改善 (Δ=${event.delta.toFixed(2)}%) — 可能漏報維修或數據誤差`,
        severity: 'CRITICAL',
        icon: '🚨'
      }
    }
    return { isAnomalous: false }
  }

  // 其他維修：應該改善（delta < 0）
  if (event.delta >= 0) {
    if (event.delta > 5) {
      return {
        isAnomalous: true,
        reason: `🔴 嚴重異常：維修後大幅惡化 (Δ=${event.delta.toFixed(2)}%) — 需立即檢查`,
        severity: 'CRITICAL',
        icon: '🚨'
      }
    } else {
      return {
        isAnomalous: true,
        reason: `🟡 異常：維修無效 (Δ=${event.delta.toFixed(2)}%) — 需檢查維修質量`,
        severity: 'WARNING',
        icon: '⚠️'
      }
    }
  }

  // delta < 0：改善，成功
  return { isAnomalous: false }
}

/**
 * 獲取維修效果描述
 */
export function getMaintenanceResult(delta: number | null, is_uwi_only?: boolean): string {
  if (delta === null) return '數據不足'
  if (is_uwi_only) {
    if (delta < -1.0) return '⚠️ 異常改善'
    return '✓ 正常（無改善）'
  }

  if (delta < -10) return '🟢 卓越改善'
  if (delta < -5) return '🟢 良好改善'
  if (delta < -2) return '🟢 輕度改善'
  if (delta < 0) return '🟡 微弱改善'
  if (delta <= 5) return '🟡 無改善'
  return '🔴 嚴重惡化'
}

/**
 * 統計摘要
 */
export const ANOMALY_STATS = {
  description: '基於 74 個維護事件的數據分析',
  totalEvents: 74,
  successfulMaintenance: 41,
  successRate: 55.4,
  anomalousEvents: 33,
  anomalyRate: 44.6,
  categories: {
    excellent: 25, // Δ < -10%
    good: 7, // -10% ≤ Δ < -5%
    ok: 9, // -5% ≤ Δ < -2%
    poor: 0, // -2% ≤ Δ < 0%
    critical: 33 // Δ ≥ 0%
  }
}
