// Mock "API" layer. Shaped to mirror the real endpoints described in
// design_docs/fleet-dashboard-frontend-requirements.md section 6, and the
// backend Pydantic schemas in backend/app/schemas.py, so swapping this out
// for real fetch() calls later is a drop-in replacement.

import { VESSEL_REFS, UWI_INSPECTIONS, MAINTENANCE_LOG, VESSEL_LIVE_STATE } from './reference'
import { getSeriesForVessel, getAllSeries } from './noonReports'
import { addDays, createRng, daysBetween, randRange, MOCK_TODAY } from './seed'
import type {
  VesselSummary,
  FoulingGrade,
  InspectionEntry,
  HullSectionFouling,
  SpeedLossSeries,
  FuelAttributionResponse,
  MaintenanceRecommendation,
  FleetKpis,
  Urgency,
  MaintenanceCorrelationResponse,
  MaintenanceEffectivenessEvent,
  MaintenanceTypeEffectiveness,
  MaintenanceEventType,
  PerformanceTimelinePoint,
  OptimalMaintenanceTiming,
} from '@/types/fleet'

// simulate network latency so Loading states are exercised
const LATENCY_MS = 260

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS))
}

function biofoulingScoreToGrade(score: number): FoulingGrade {
  if (score < 25) return 'Clean'
  if (score < 50) return 'Light'
  if (score < 80) return 'Moderate'
  return 'Heavy'
}

function speedLossToGrade(pct: number): FoulingGrade {
  if (pct < 3) return 'Clean'
  if (pct < 7) return 'Light'
  if (pct < 13) return 'Moderate'
  return 'Heavy'
}

function currentSpeedLoss(imo: string): number {
  const series = getSeriesForVessel(imo)
  if (!series || series.reports.length === 0) return 0
  return series.reports[series.reports.length - 1].speedLossPct
}

function degradationRate(imo: string): number {
  const series = getSeriesForVessel(imo)
  if (!series) return 0
  const reports = series.reports
  const last = reports[reports.length - 1]
  const lastClean = [...series.hullCleaningDates].filter((d) => d <= last.date).pop() ?? reports[0].date
  const window = reports.filter((r) => r.date >= lastClean)
  if (window.length < 5) return 0.01
  const first = window[0]
  const days = Math.max(1, daysBetween(first.date, last.date))
  return Number(((last.speedLossPct - first.speedLossPct) / days).toFixed(4))
}

function urgencyFor(speedLossPct: number): Urgency {
  if (speedLossPct >= 8) return 'HIGH'
  if (speedLossPct >= 5) return 'MEDIUM'
  return 'LOW'
}

function excessFuelCostThisMonth(imo: string): number {
  const series = getSeriesForVessel(imo)
  if (!series) return 0
  const monthAgo = addDays(MOCK_TODAY, -30)
  const recent = series.reports.filter((r) => r.date >= monthAgo)
  const rng = createRng(imo + '-cost')
  const fuelPriceUsdPerMt = 620
  const excessMt = recent.reduce((sum, r) => {
    const baselineFuel = r.fuelConsumptionMt / (1 + Math.max(r.speedLossPct, 0) / 100 * 1.8)
    return sum + Math.max(0, r.fuelConsumptionMt - baselineFuel)
  }, 0)
  return Math.round(excessMt * fuelPriceUsdPerMt * randRange(rng, 0.95, 1.05))
}

function nextRecommendedWindow(imo: string): { start: string; end: string } {
  const rate = degradationRate(imo)
  const loss = currentSpeedLoss(imo)
  const daysToThreshold = rate > 0 ? Math.max(5, Math.round((8 - loss) / rate)) : 120
  const start = addDays(MOCK_TODAY, Math.max(3, daysToThreshold - 7))
  const end = addDays(MOCK_TODAY, Math.max(10, daysToThreshold + 7))
  return { start, end }
}

function buildVesselSummary(imo: string): VesselSummary {
  const ref = VESSEL_REFS.find((v) => v.imo === imo)!
  const live = VESSEL_LIVE_STATE[imo]
  const series = getSeriesForVessel(imo)!
  const lastReport = series.reports[series.reports.length - 1]
  const lastClean = [...series.hullCleaningDates].pop() ?? ref.lastDrydockDate
  const speedLossPct = currentSpeedLoss(imo)

  return {
    imo,
    name: ref.name,
    type: ref.vesselType,
    teuCapacity: ref.teuCapacity,
    builtYear: ref.builtYear,
    flag: ref.flag,
    mainEngineModel: ref.mainEngineModel,
    designSpeedKt: ref.designSpeedKt,
    tradeRoute: ref.tradeRoute,
    status: live.status,
    currentPort: live.currentPort,
    destinationPort: live.destinationPort,
    position: {
      lat: live.lat,
      lon: live.lon,
      headingDeg: live.headingDeg,
      speedKt: live.speedKt,
      courseTrueDeg: live.headingDeg,
    },
    speedLossPct: Number(speedLossPct.toFixed(2)),
    foulingGrade: speedLossToGrade(speedLossPct),
    lastDrydockDate: ref.lastDrydockDate,
    nextDrydockDue: ref.nextDrydockDue,
    daysSinceHullClean: daysBetween(lastClean, lastReport?.date ?? MOCK_TODAY),
    maintenanceUrgency: urgencyFor(speedLossPct),
    degradationRatePctPerDay: degradationRate(imo),
    excessFuelCostUsdMtd: excessFuelCostThisMonth(imo),
    nextRecommendedWindow: nextRecommendedWindow(imo),
  }
}

export async function fetchFleetKpis(): Promise<FleetKpis> {
  const summaries = VESSEL_REFS.map((v) => buildVesselSummary(v.imo))
  return delay({
    totalVessels: summaries.length,
    underway: summaries.filter((s) => s.status === 'underway').length,
    inPort: summaries.filter((s) => s.status !== 'underway').length,
    pendingMaintenance: summaries.filter((s) => s.maintenanceUrgency !== 'LOW').length,
    monthlyExcessFuelCostUsd: summaries.reduce((sum, s) => sum + s.excessFuelCostUsdMtd, 0),
  })
}

export async function fetchFleetVessels(): Promise<VesselSummary[]> {
  return delay(VESSEL_REFS.map((v) => buildVesselSummary(v.imo)))
}

export async function fetchVessel(imo: string): Promise<VesselSummary | null> {
  const ref = VESSEL_REFS.find((v) => v.imo === imo)
  if (!ref) return delay(null)
  return delay(buildVesselSummary(imo))
}

export async function fetchNoonReports(imo: string): Promise<{ vessel: VesselSummary; reports: import('@/types/fleet').NoonReportEntry[] } | null> {
  const vessel = await fetchVessel(imo)
  const series = getSeriesForVessel(imo)
  if (!vessel || !series) return null
  return delay({ vessel, reports: series.reports })
}

const HULL_SECTIONS: HullSectionFouling['section'][] = [
  'bow',
  'forward-flat',
  'aft-flat',
  'stern',
  'port-side',
  'starboard-side',
  'propeller',
  'rudder',
]

export async function fetchInspections(imo: string): Promise<InspectionEntry[]> {
  const rows = UWI_INSPECTIONS.filter((u) => u.imo === imo)
  const rng = createRng(imo + '-inspections')
  const entries: InspectionEntry[] = rows.map((row) => {
    const overallGrade = biofoulingScoreToGrade(row.biofoulingScore)
    const hullSections: HullSectionFouling[] = HULL_SECTIONS.map((section) => {
      const jitter = randRange(rng, -18, 12)
      const sectionScore = Math.max(0, Math.min(100, row.biofoulingScore + jitter))
      return { section, grade: biofoulingScoreToGrade(sectionScore) }
    })
    return {
      id: row.id,
      date: row.date,
      port: row.port,
      surveyor: row.surveyor,
      method: row.method,
      foulingGrade: overallGrade,
      biofoulingScore: row.biofoulingScore,
      paintBreakdownPct: row.paintBreakdownPct,
      propellerCondition: row.propellerCondition,
      cleaningRecommended: row.cleaningRecommended,
      notes: row.notes,
      hullSections,
      photoCount: Math.round(randRange(rng, 4, 14)),
      reportUrl: null,
    }
  })
  return delay(entries.sort((a, b) => (a.date < b.date ? 1 : -1)))
}

export async function fetchSpeedLoss(imo: string): Promise<SpeedLossSeries | null> {
  const ref = VESSEL_REFS.find((v) => v.imo === imo)
  const series = getSeriesForVessel(imo)
  if (!ref || !series) return null
  return delay({
    vessel: { imo, name: ref.name, type: ref.vesselType },
    cleanBaseline: { speedKnots: ref.designSpeedKt, source: 'sea_trial' },
    events: series.events,
    reports: series.reports,
  })
}

const FACTOR_LABELS: Record<string, string> = {
  weather: '天氣（風浪）',
  hull_fouling: '船體污損',
  propeller_fouling: '螺旋槳污損',
  engine_degradation: '主機老化',
}

export async function fetchFuelAttribution(imo: string): Promise<FuelAttributionResponse | null> {
  const ref = VESSEL_REFS.find((v) => v.imo === imo)
  const series = getSeriesForVessel(imo)
  if (!ref || !series) return null

  const rng = createRng(imo + '-attribution')
  const recent = series.reports.slice(-60)
  const timeSeries = recent.map((r) => {
    const weather = r.beaufort >= 4 ? randRange(rng, 0.3, 1.4) * (r.beaufort / 5) : randRange(rng, 0.05, 0.3)
    const hullShare = Math.max(0, r.speedLossPct) * 0.65
    const propShare = Math.max(0, r.speedLossPct) * 0.2
    const engineShare = Math.max(0, r.speedLossPct) * 0.08
    const scale = r.fuelConsumptionMt / 100
    return {
      date: r.date,
      weather: Number(weather.toFixed(2)),
      hull_fouling: Number((hullShare * scale).toFixed(2)),
      propeller_fouling: Number((propShare * scale).toFixed(2)),
      engine_degradation: Number((engineShare * scale).toFixed(2)),
    }
  })

  const last = recent[recent.length - 1]
  const baselineFuelMt = Number((last.fuelConsumptionMt / (1 + Math.max(last.speedLossPct, 0) / 100 * 1.8)).toFixed(2))
  const latest = timeSeries[timeSeries.length - 1]
  const actualFuelMt = Number(
    (baselineFuelMt + latest.weather + latest.hull_fouling + latest.propeller_fouling + latest.engine_degradation).toFixed(2),
  )

  const attribution = [
    { factor: 'weather' as const, impactMt: latest.weather, label: FACTOR_LABELS.weather },
    { factor: 'hull_fouling' as const, impactMt: latest.hull_fouling, label: FACTOR_LABELS.hull_fouling },
    { factor: 'propeller_fouling' as const, impactMt: latest.propeller_fouling, label: FACTOR_LABELS.propeller_fouling },
    { factor: 'engine_degradation' as const, impactMt: latest.engine_degradation, label: FACTOR_LABELS.engine_degradation },
  ]

  const inspectionCount = UWI_INSPECTIONS.filter((u) => u.imo === imo).length
  const confidence = inspectionCount >= 4 ? 'high' : inspectionCount >= 2 ? 'medium' : 'low'

  return delay({ baselineFuelMt, actualFuelMt, attribution, confidence, timeSeries })
}

export async function fetchMaintenanceRecommendation(imo: string): Promise<MaintenanceRecommendation | null> {
  const ref = VESSEL_REFS.find((v) => v.imo === imo)
  const series = getSeriesForVessel(imo)
  if (!ref || !series) return null

  const speedLossPct = currentSpeedLoss(imo)
  const rate = degradationRate(imo)
  const window = nextRecommendedWindow(imo)

  const rng = createRng(imo + '-advisor')
  const cleaningEvents = MAINTENANCE_LOG.filter((m) => m.imo === imo && m.type === 'Hull Cleaning')
  const avgCost = cleaningEvents.length
    ? cleaningEvents.reduce((s, e) => s + e.costUsd, 0) / cleaningEvents.length
    : 30000
  const fuelPriceUsdPerMt = 620

  const curve = Array.from({ length: 91 }, (_, i) => {
    const deferralDays = i
    const projectedLoss = Math.max(0, speedLossPct + rate * deferralDays)
    const excessFuelMtPerDay = ref.baselineDailyFuelMt * (projectedLoss / 100) * 1.8
    const cumulativeExcessFuelCostUsd = Math.round(
      excessFuelMtPerDay * fuelPriceUsdPerMt * deferralDays * 0.55, // 0.55 ~ average of ramp from 0 to full
    )
    // opportunity cost of executing NOW increases the further out you'd rather wait for a scheduled port call
    const opportunityCostUsd = Math.round(avgCost * (1 - deferralDays / 220) * randRange(rng, 0.98, 1.02))
    return {
      deferralDays,
      cumulativeExcessFuelCostUsd,
      opportunityCostUsd: Math.max(opportunityCostUsd, avgCost * 0.35),
    }
  })

  const inspectionCount = UWI_INSPECTIONS.filter((u) => u.imo === imo).length
  const confidence = inspectionCount >= 4 ? 'high' : inspectionCount >= 2 ? 'medium' : 'low'

  const estimatedSavingUsd = Math.round(
    curve.reduce((max, p) => Math.max(max, p.cumulativeExcessFuelCostUsd - p.opportunityCostUsd + avgCost), 0),
  )

  const dataLimitations: string[] = []
  if (inspectionCount < 4) {
    dataLimitations.push(`本船僅有 ${inspectionCount} 次水下檢查記錄，趨勢估計信心中等。`)
  }
  if (cleaningEvents.length < 2) {
    dataLimitations.push('歷史清潔事件樣本不足，成本估算採用船隊平均值。')
  }

  return delay({
    action: 'hull_cleaning',
    windowStart: window.start,
    windowEnd: window.end,
    estimatedSavingUsd,
    confidence,
    reasoning:
      rate > (foulingRateBenchmark() * 1.2)
        ? `船體污損增長速率 (${(rate * 30).toFixed(2)}%/月) 高於船隊平均，建議提前安排。`
        : `船體污損增長速率 (${(rate * 30).toFixed(2)}%/月) 接近船隊平均，建議依標準週期安排。`,
    dataLimitations,
    curve,
  })
}

function foulingRateBenchmark(): number {
  const all = getAllSeries()
  let sum = 0
  let count = 0
  for (const [imo] of all) {
    sum += degradationRate(imo)
    count++
  }
  return count ? sum / count : 0.02
}

// ─── Maintenance-Performance Correlation Analysis ─────────────────────────────

export async function fetchMaintenanceCorrelation(imo: string): Promise<MaintenanceCorrelationResponse | null> {
  const ref = VESSEL_REFS.find((v) => v.imo === imo)
  const series = getSeriesForVessel(imo)
  if (!ref || !series) return null

  const reports = series.reports

  // Build performance timeline (downsample to every 4th point for chart performance)
  const timeline: PerformanceTimelinePoint[] = reports
    .filter((_, i) => i % 2 === 0)
    .map((r) => ({
      date: r.date,
      fuelConsumptionMt: r.fuelConsumptionMt,
      speedLossPct: r.speedLossPct,
    }))

  // Get maintenance events for this vessel
  const maintEvents = MAINTENANCE_LOG.filter((m) => m.imo === imo).sort((a, b) =>
    a.date < b.date ? -1 : 1,
  )

  // For each maintenance event, compute before/after metrics
  const WINDOW_DAYS = 5
  const effectivenessEvents: MaintenanceEffectivenessEvent[] = []

  for (const evt of maintEvents) {
    const evtDate = evt.date

    // Find reports in the 5-day window before and after the event
    const before = reports.filter((r) => {
      const diff = daysBetween(r.date, evtDate)
      return diff >= 1 && diff <= WINDOW_DAYS
    })
    const after = reports.filter((r) => {
      const diff = daysBetween(evtDate, r.date)
      return diff >= 1 && diff <= WINDOW_DAYS
    })

    if (before.length === 0 || after.length === 0) continue

    const fuelBefore = before.reduce((s, r) => s + r.fuelConsumptionMt, 0) / before.length
    const fuelAfter = after.reduce((s, r) => s + r.fuelConsumptionMt, 0) / after.length
    const speedLossBefore = before.reduce((s, r) => s + r.speedLossPct, 0) / before.length
    const speedLossAfter = after.reduce((s, r) => s + r.speedLossPct, 0) / after.length

    const fuelImprovementMt = fuelBefore - fuelAfter
    const improvementPct = fuelBefore > 0 ? (fuelImprovementMt / fuelBefore) * 100 : 0

    // Determine event type (combine Hull Cleaning + PP if within 7 days)
    let eventType: MaintenanceEventType = evt.type as MaintenanceEventType
    const nearbyPP = maintEvents.find(
      (m) =>
        m.id !== evt.id &&
        m.type === 'Propeller Polishing' &&
        Math.abs(daysBetween(evt.date, m.date)) <= 7 &&
        evt.type === 'Hull Cleaning',
    )
    if (nearbyPP) {
      eventType = 'Hull Cleaning + PP'
    }
    // Skip the PP entry if it's already part of a combined event
    if (
      evt.type === 'Propeller Polishing' &&
      maintEvents.some(
        (m) =>
          m.id !== evt.id &&
          m.type === 'Hull Cleaning' &&
          Math.abs(daysBetween(evt.date, m.date)) <= 7,
      )
    ) {
      continue
    }

    // Anomaly detection
    let isAnomaly = false
    let anomalyReason: string | null = null
    if (eventType === 'Hull Cleaning' && improvementPct < 1) {
      isAnomaly = true
      anomalyReason = '船體清洗後油耗未見明顯改善，可能需進一步檢查防污漆狀態。'
    } else if (eventType === 'Propeller Polishing' && improvementPct > 10) {
      isAnomaly = true
      anomalyReason = '螺旋槳拋光後改善幅度異常高，建議確認是否有其他因素影響。'
    }

    effectivenessEvents.push({
      id: evt.id,
      date: evtDate,
      type: eventType,
      port: evt.port,
      fuelBefore: Number(fuelBefore.toFixed(2)),
      fuelAfter: Number(fuelAfter.toFixed(2)),
      fuelImprovementMt: Number(fuelImprovementMt.toFixed(2)),
      improvementPct: Number(improvementPct.toFixed(1)),
      speedLossBefore: Number(speedLossBefore.toFixed(2)),
      speedLossAfter: Number(speedLossAfter.toFixed(2)),
      isAnomaly,
      anomalyReason,
      costUsd: evt.costUsd + (nearbyPP ? nearbyPP.costUsd : 0),
    })
  }

  // Aggregate by type
  const typeMap = new Map<MaintenanceEventType, MaintenanceEffectivenessEvent[]>()
  for (const evt of effectivenessEvents) {
    const arr = typeMap.get(evt.type) || []
    arr.push(evt)
    typeMap.set(evt.type, arr)
  }

  const typeEffectiveness: MaintenanceTypeEffectiveness[] = []
  for (const [type, events] of typeMap) {
    const avgImprovement = events.reduce((s, e) => s + e.improvementPct, 0) / events.length
    const avgFuelImprovement = events.reduce((s, e) => s + e.fuelImprovementMt, 0) / events.length
    const avgCost = events.reduce((s, e) => s + e.costUsd, 0) / events.length
    const costPerPct = avgImprovement > 0 ? avgCost / avgImprovement : Infinity

    let rating = 1
    if (avgImprovement >= 10) rating = 5
    else if (avgImprovement >= 6) rating = 4
    else if (avgImprovement >= 3) rating = 3
    else if (avgImprovement >= 1) rating = 2

    typeEffectiveness.push({
      type,
      eventCount: events.length,
      avgFuelImprovementMt: Number(avgFuelImprovement.toFixed(2)),
      avgImprovementPct: Number(avgImprovement.toFixed(1)),
      avgCostUsd: Math.round(avgCost),
      costPerPctImprovement: Number(costPerPct.toFixed(0)),
      rating,
    })
  }

  typeEffectiveness.sort((a, b) => b.avgImprovementPct - a.avgImprovementPct)

  // Summary
  const totalFuelSavedMt = effectivenessEvents.reduce((s, e) => s + Math.max(0, e.fuelImprovementMt), 0)
  const totalCost = effectivenessEvents.reduce((s, e) => s + e.costUsd, 0)
  const avgImprovementPct =
    effectivenessEvents.length > 0
      ? effectivenessEvents.reduce((s, e) => s + e.improvementPct, 0) / effectivenessEvents.length
      : 0

  const bestEvent = effectivenessEvents.reduce(
    (best, e) => (e.improvementPct > (best?.improvementPct ?? -Infinity) ? e : best),
    effectivenessEvents[0],
  )
  const worstEvent = effectivenessEvents.reduce(
    (worst, e) => (e.improvementPct < (worst?.improvementPct ?? Infinity) ? e : worst),
    effectivenessEvents[0],
  )

  // ─── Optimal Maintenance Timing Recommendation ────────────────────────────
  const currentSL = currentSpeedLoss(imo)
  const rate = degradationRate(imo)
  const fuelPriceUsdPerMt = 620

  // Determine optimal threshold based on historical data:
  // When past interventions were most cost-effective (best improvement-to-cost ratio)
  const optimalThreshold = 8 // % speed loss — based on industry ISO 19030 guidance
  const daysUntilThreshold = rate > 0 ? Math.max(0, Math.round((optimalThreshold - currentSL) / rate)) : 90

  // Determine recommended action based on current fouling level
  let recommendedAction: MaintenanceEventType = 'Hull Cleaning'
  if (currentSL >= 12) recommendedAction = 'Hull Cleaning + PP'
  else if (currentSL < 4) recommendedAction = 'Propeller Polishing'

  const excessFuelPerDay = ref.baselineDailyFuelMt * (currentSL / 100) * 1.8
  const excessFuelCostPerDayUsd = Math.round(excessFuelPerDay * fuelPriceUsdPerMt)

  // Project savings: fuel saved over 90 days post-maintenance vs doing nothing
  const avgBestImprovement = typeEffectiveness.length > 0 ? typeEffectiveness[0].avgImprovementPct : 5
  const projectedFuelSavedMtPerDay = ref.baselineDailyFuelMt * (avgBestImprovement / 100) * 1.8
  const projectedSavingsUsd = Math.round(projectedFuelSavedMtPerDay * fuelPriceUsdPerMt * 90)

  const windowStart = addDays(MOCK_TODAY, daysUntilThreshold)
  const windowEnd = addDays(MOCK_TODAY, daysUntilThreshold + 14)

  let urgency: 'LOW' | 'MEDIUM' | 'HIGH' = 'LOW'
  if (currentSL >= 10 || daysUntilThreshold <= 7) urgency = 'HIGH'
  else if (currentSL >= 6 || daysUntilThreshold <= 30) urgency = 'MEDIUM'

  let reasoning: string
  if (urgency === 'HIGH') {
    reasoning = `目前 Speed Loss ${currentSL.toFixed(1)}% 已超過經濟效益閾值 (${optimalThreshold}%)，每日超額油耗成本約 $${excessFuelCostPerDayUsd.toLocaleString()}。建議立即安排 ${recommendedAction}，預估 90 天內可節省 $${projectedSavingsUsd.toLocaleString()}。`
  } else if (urgency === 'MEDIUM') {
    reasoning = `目前 Speed Loss ${currentSL.toFixed(1)}%，以目前衰退速率 (${(rate * 30).toFixed(2)}%/月) 推算，約 ${daysUntilThreshold} 天後將達到最佳介入閾值 (${optimalThreshold}%)。建議提前安排港口排程。`
  } else {
    reasoning = `目前 Speed Loss ${currentSL.toFixed(1)}% 處於正常範圍，污損增長率 ${(rate * 30).toFixed(2)}%/月。建議依標準週期於預估窗口期安排維護。`
  }

  const optimalTiming: OptimalMaintenanceTiming = {
    recommendedAction,
    currentSpeedLossPct: Number(currentSL.toFixed(1)),
    degradationRatePerDay: Number(rate.toFixed(4)),
    optimalThresholdPct: optimalThreshold,
    daysUntilThreshold,
    windowStart,
    windowEnd,
    excessFuelCostPerDayUsd,
    projectedSavingsUsd,
    reasoning,
    urgency,
  }

  return delay({
    vessel: { imo, name: ref.name },
    timeline,
    events: effectivenessEvents,
    typeEffectiveness,
    optimalTiming,
    summary: {
      totalEvents: effectivenessEvents.length,
      avgImprovementPct: Number(avgImprovementPct.toFixed(1)),
      bestEventId: bestEvent?.id ?? '',
      worstEventId: worstEvent?.id ?? '',
      anomalyCount: effectivenessEvents.filter((e) => e.isAnomaly).length,
      totalMaintenanceCostUsd: totalCost,
      totalFuelSavedMt: Number(totalFuelSavedMt.toFixed(1)),
    },
  })
}
