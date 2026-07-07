import type { Vessel } from '@/data/mockFleet'
import { computeDailyFoc } from '@/data/mockFleet'
import { predictMaintenanceWindow, type MaintenancePrediction } from '@/utils/predictiveMaintenance'

export interface VesselReportRow {
  vessel: Vessel
  dailyFoc: number
  prediction: MaintenancePrediction
}

export interface FleetReport {
  generatedAt: string
  rows: VesselReportRow[]
  avgSpeedLossPct: number
  avgDailyFoc: number
  attentionCount: number
}

function timestamp(): string {
  return new Date().toISOString().slice(0, 16).replace('T', ' ')
}

function statusText(status: Vessel['status']): string {
  return status === 'critical' ? '高風險' : status === 'warning' ? '警示' : '正常'
}

export function buildFleetReport(vessels: Vessel[]): FleetReport {
  const rows: VesselReportRow[] = vessels.map((vessel) => ({
    vessel,
    dailyFoc: Number(computeDailyFoc(vessel.noon_reports[vessel.noon_reports.length - 1]).toFixed(1)),
    prediction: predictMaintenanceWindow(vessel)
  }))
  const avgSpeedLossPct = Number((vessels.reduce((s, v) => s + v.speed_loss_pct, 0) / vessels.length).toFixed(1))
  const avgDailyFoc = Number((rows.reduce((s, r) => s + r.dailyFoc, 0) / rows.length).toFixed(1))
  const attentionCount = vessels.filter((v) => v.status !== 'normal').length

  return { generatedAt: timestamp(), rows, avgSpeedLossPct, avgDailyFoc, attentionCount }
}

export function fleetReportToMarkdown(report: FleetReport): string {
  const lines: string[] = []
  lines.push('# 船隊節能分析報告')
  lines.push('')
  lines.push(`產出時間：${report.generatedAt}`)
  lines.push('')
  lines.push('## 船隊總覽')
  lines.push(`- 船隊總數：${report.rows.length} 艘`)
  lines.push(`- 平均 Speed Loss：${report.avgSpeedLossPct}%`)
  lines.push(`- 平均 Daily FOC：${report.avgDailyFoc} t/day`)
  lines.push(`- 需關注船舶：${report.attentionCount} 艘`)
  lines.push('')
  lines.push('## 各船狀態與維修建議')
  lines.push('')
  lines.push('| 船名 | 航線 | Speed Loss | Daily FOC | 狀態 | 建議清潔窗口 | 預估可節省油耗 |')
  lines.push('| --- | --- | --- | --- | --- | --- | --- |')
  for (const row of report.rows) {
    lines.push(
      `| ${row.vessel.name} | ${row.vessel.route} | ${row.vessel.speed_loss_pct}% | ${row.dailyFoc} t/day | ${statusText(row.vessel.status)} | ${row.prediction.recommendedDate} | ${row.prediction.estFuelSavingTDay} t/day |`
    )
  }
  lines.push('')
  lines.push('## 資料來源與計算方法')
  lines.push('- 資料來源：15 艘船 2021-2025 每日正午報表（已過濾 WIND_SCALE ≤ 4、HOURS_FULL_SPEED ≥ 22h）')
  lines.push('- Daily FOC = ME_FULLSPEED_CONSUMP_VLSFO ÷ HOURS_FULL_SPEED × 24')
  lines.push('- 本報告為 Demo 模擬資料，正式 ISO 15016 / ISO 19030 計算條文待節能小組補上')
  lines.push('')
  return lines.join('\n')
}

export function vesselReportToMarkdown(vessel: Vessel): string {
  const dailyFoc = Number(computeDailyFoc(vessel.noon_reports[vessel.noon_reports.length - 1]).toFixed(1))
  const prediction = predictMaintenanceWindow(vessel)

  const lines: string[] = []
  lines.push(`# ${vessel.name} 節能分析報告`)
  lines.push('')
  lines.push(`產出時間：${timestamp()}`)
  lines.push('')
  lines.push(`- 航線：${vessel.route}`)
  lines.push(`- 航速：${vessel.speed_knots} knots`)
  lines.push(`- Speed Loss：${vessel.speed_loss_pct}%`)
  lines.push(`- Daily FOC：${dailyFoc} t/day`)
  lines.push(`- 狀態：${statusText(vessel.status)}`)
  lines.push('')
  lines.push('## 維修排程建議')
  if (prediction.breached) {
    lines.push(`Speed Loss 已超過門檻，建議於下次靠港（${prediction.recommendedDate}）安排水下清潔，預估可節省 ${prediction.estFuelSavingTDay} t/day 油耗。`)
  } else if (prediction.daysToBreach !== null) {
    lines.push(`預計 ${prediction.daysToBreach} 天後達門檻，建議規劃於 ${prediction.recommendedDate} 靠港時清潔，預估可節省 ${prediction.estFuelSavingTDay} t/day 油耗。`)
  } else {
    lines.push('目前效能穩定，暫無需提前安排清潔。')
  }
  lines.push('')
  lines.push('## 近 14 日午報趨勢')
  lines.push('| 日期 | WIND_SCALE | HOURS_FULL_SPEED | ME_FULLSPEED_CONSUMP_VLSFO | Speed Loss % | Daily FOC |')
  lines.push('| --- | --- | --- | --- | --- | --- |')
  for (const r of vessel.noon_reports) {
    lines.push(`| ${r.date} | ${r.WIND_SCALE} | ${r.HOURS_FULL_SPEED} | ${r.ME_FULLSPEED_CONSUMP_VLSFO} | ${r.speed_loss_pct}% | ${computeDailyFoc(r).toFixed(1)} |`)
  }
  lines.push('')
  return lines.join('\n')
}
