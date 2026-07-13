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
