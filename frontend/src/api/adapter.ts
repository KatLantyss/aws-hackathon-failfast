/**
 * Real data adapter — fetches from backend API endpoints and transforms
 * into the frontend's type system. No local CSV files needed.
 */

import type {
  SpeedLossSeries,
  SpeedLossEvent,
  NoonReportEntry,
  VesselSummary,
  FoulingGrade,
  Urgency,
  FleetKpis,
  MaintenanceRecommendation,
  Confidence,
  CostBenefitPoint,
  MaintenanceCorrelationResponse,
  MaintenanceEffectivenessEvent,
  MaintenanceTypeEffectiveness,
  MaintenanceEventType,
  PerformanceTimelinePoint,
  OptimalMaintenanceTiming,
} from '@/types/fleet'

import {
  fetchApiVessels,
  fetchApiVesselDetail,
  fetchApiSpeedLoss,
  fetchApiMaintenanceEvents,
  fetchApiFleetRanking,
  fetchApiFleetSummary,
  fetchApiNoonReports,
  type ApiSpeedLossPoint,
  type ApiMaintenanceEvent,
  type ApiFleetRankingEntry,
  type ApiFleetSummaryVessel,
} from '@/api/client'

// ─── Constants ────────────────────────────────────────────────────────────────

const W1_SHIPS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S21']
const W2_SHIPS = ['S9', 'S10', 'S11', 'S12', 'S22', 'S23']
const ALL_SHIPS = [...W1_SHIPS, ...W2_SHIPS]

// Day 0 = 2020-01-01 (arbitrary baseline for display)
const BASE_DATE = new Date('2020-01-01')
function dayToDate(day: number): string {
  const d = new Date(BASE_DATE)
  d.setDate(d.getDate() + day)
  return d.toISOString().slice(0, 10)
}

// Maintenance event type mapping
const EVENT_TYPE_MAP: Record<string, SpeedLossEvent['type']> = {
  PP: 'propeller_polishing',
  'UWI+PP': 'propeller_polishing',
  UWC: 'hull_cleaning',
  'UWC+PP': 'hull_cleaning',
  DD: 'drydock',
  UWI: 'hull_cleaning',
}
const EVENT_LABEL_MAP: Record<string, string> = {
  PP: '螺旋槳拋光',
  'UWI+PP': '水下檢查+拋光',
  UWC: '船殼清洗',
  'UWC+PP': '清洗+拋光',
  DD: '進塢',
  UWI: '水下檢查',
}
const CORRELATION_TYPE_MAP: Record<string, MaintenanceEventType> = {
  DD: 'Hull Cleaning + PP',
  'UWC+PP': 'Hull Cleaning + PP',
  UWC: 'Hull Cleaning',
  'UWI+PP': 'Propeller Polishing',
  PP: 'Propeller Polishing',
  UWI: 'Propeller Polishing',
}

// ─── Public API ───────────────────────────────────────────────────────────────

export function getRealShipList(): string[] {
  return ALL_SHIPS
}

export async function fetchRealFleetVessels(): Promise<VesselSummary[]> {
  const summary = await fetchApiFleetSummary()
  return summary.per_vessel.map((v) =>
    buildVesselSummaryFromSummary(v),
  )
}

export async function fetchRealFleetKpis(): Promise<FleetKpis> {
  const summary = await fetchApiFleetSummary()
  return {
    totalVessels: summary.total_vessels,
    underway: 0,
    inPort: 0,
    pendingMaintenance: summary.pending_maintenance,
    monthlyExcessFuelCostUsd: summary.total_excess_fuel_cost_usd_per_day,
  }
}

export async function fetchRealVesselSummary(shipId: string): Promise<VesselSummary | null> {
  try {
    const [detail, ranking, maintResp] = await Promise.all([
      fetchApiVesselDetail(shipId),
      fetchApiFleetRanking(),
      fetchApiMaintenanceEvents(shipId),
    ])
    const rank = ranking.fleet_ranking.find((r) => r.vessel_id === shipId)
    const lastMaintDay = maintResp.events.length
      ? Math.max(...maintResp.events.map((e) => e.event_day))
      : 0
    return buildVesselSummary(shipId, detail.avg_consumption, rank, lastMaintDay, detail.total_records)
  } catch {
    return null
  }
}

export async function fetchRealSpeedLoss(shipId: string): Promise<SpeedLossSeries | null> {
  try {
    const [slResp, maintResp] = await Promise.all([
      fetchApiSpeedLoss(shipId),
      fetchApiMaintenanceEvents(shipId),
    ])

    const designSpeed = W1_SHIPS.includes(shipId) ? 22.5 : 21.0
    const data = slResp.speed_loss_data

    const reports: NoonReportEntry[] = data.map((p) => ({
      date: dayToDate(p.noon_day),
      lat: 0,
      lon: 0,
      observedSpeedKt: p.stw,
      correctedSpeedKt: p.ref_stw,
      speedLossPct: p.ref_stw > 0 ? ((p.ref_stw - p.stw) / p.ref_stw) * 100 : 0,
      fuelConsumptionMt: 0,
      beaufort: p.wind_scale,
      seaState: p.wind_scale,
      draftFwd: 0,
      draftAft: 0,
      loadCondition: 'laden' as const,
      isAnomaly: false,
      anomalyReason: null,
    }))

    const events: SpeedLossEvent[] = maintResp.events.map((e) => ({
      date: dayToDate(e.event_day),
      type: EVENT_TYPE_MAP[e.event_type] || 'hull_cleaning',
      label: EVENT_LABEL_MAP[e.event_type] || e.event_type,
    }))

    return {
      vessel: { imo: shipId, name: shipId, type: W1_SHIPS.includes(shipId) ? 'W1' : 'W2' },
      cleanBaseline: { speedKnots: designSpeed, source: 'post_maintenance' },
      events,
      reports,
    }
  } catch {
    return null
  }
}

export async function fetchRealMaintenanceRecommendation(shipId: string): Promise<MaintenanceRecommendation | null> {
  const vessel = await fetchRealVesselSummary(shipId)
  if (!vessel) return null

  const rate = vessel.degradationRatePctPerDay
  const speedLossPct = vessel.speedLossPct
  const avgConsumption = vessel.designSpeedKt > 21 ? 155 : 92 // rough baseline
  const fuelPrice = 620
  const cleaningCost = 30000

  const curve: CostBenefitPoint[] = Array.from({ length: 91 }, (_, i) => {
    const projectedLoss = Math.max(0, speedLossPct + rate * i)
    const excessFuelPerDay = avgConsumption * (projectedLoss / 100) * 1.8
    return {
      deferralDays: i,
      cumulativeExcessFuelCostUsd: Math.round(excessFuelPerDay * fuelPrice * i * 0.55),
      opportunityCostUsd: Math.round(cleaningCost * (1 - i / 220)),
    }
  })

  const confidence: Confidence = 'medium'

  return {
    action: 'hull_cleaning',
    windowStart: vessel.nextRecommendedWindow.start,
    windowEnd: vessel.nextRecommendedWindow.end,
    estimatedSavingUsd: Math.round(curve[60]?.cumulativeExcessFuelCostUsd || 50000),
    confidence,
    reasoning: `Speed Loss ${speedLossPct.toFixed(1)}%，衰退速率 ${(rate * 30).toFixed(2)}%/月。`,
    dataLimitations: [],
    curve,
  }
}

export async function fetchRealMaintenanceCorrelation(shipId: string): Promise<MaintenanceCorrelationResponse | null> {
  try {
    const [slResp, maintResp] = await Promise.all([
      fetchApiSpeedLoss(shipId),
      fetchApiMaintenanceEvents(shipId),
    ])

    const data = slResp.speed_loss_data
    const designSpeed = W1_SHIPS.includes(shipId) ? 22.5 : 21.0

    // Build timeline — speed_loss_kn → speed_loss_pct
    const timeline: PerformanceTimelinePoint[] = data
      .filter((_, i) => i % 3 === 0)
      .map((p) => {
        const slPct = p.ref_stw > 0 ? ((p.ref_stw - p.stw) / p.ref_stw) * 100 : 0
        return {
          date: dayToDate(p.noon_day),
          fuelConsumptionMt: 0, // not available from speed loss endpoint
          speedLossPct: Number(slPct.toFixed(2)),
        }
      })

    // Compute before/after for each maintenance event
    const WINDOW_DAYS = 10
    const effectivenessEvents: MaintenanceEffectivenessEvent[] = []

    for (const maint of maintResp.events) {
      const before = data.filter((p) => p.noon_day >= maint.event_day - WINDOW_DAYS && p.noon_day < maint.event_day)
      const after = data.filter((p) => p.noon_day > maint.event_day && p.noon_day <= maint.event_day + WINDOW_DAYS)

      if (before.length < 2 || after.length < 2) continue

      const slBefore = before.reduce((s, p) => s + (p.ref_stw > 0 ? ((p.ref_stw - p.stw) / p.ref_stw) * 100 : 0), 0) / before.length
      const slAfter = after.reduce((s, p) => s + (p.ref_stw > 0 ? ((p.ref_stw - p.stw) / p.ref_stw) * 100 : 0), 0) / after.length

      // Use theoretical cubic-law for fuel estimation
      const fuelBefore = designSpeed > 21 ? 155 * (1 + Math.max(0, slBefore) / 100 * 1.8) : 92 * (1 + Math.max(0, slBefore) / 100 * 1.8)
      const fuelAfter = designSpeed > 21 ? 155 * (1 + Math.max(0, slAfter) / 100 * 1.8) : 92 * (1 + Math.max(0, slAfter) / 100 * 1.8)
      const fuelImprovementMt = fuelBefore - fuelAfter
      const improvementPct = fuelBefore > 0 ? (fuelImprovementMt / fuelBefore) * 100 : 0

      const eventType = CORRELATION_TYPE_MAP[maint.event_type] || 'Hull Cleaning'

      let isAnomaly = false
      let anomalyReason: string | null = null
      if (maint.event_type === 'DD' && improvementPct < 2) {
        isAnomaly = true
        anomalyReason = '進塢後 Speed Loss 改善不明顯，建議確認塗裝品質。'
      } else if (maint.event_type === 'PP' && improvementPct > 15) {
        isAnomaly = true
        anomalyReason = '螺旋槳拋光改善幅度異常高，可能有其他因素。'
      }

      const costEstimate: Record<string, number> = { DD: 500000, 'UWC+PP': 45000, UWC: 35000, 'UWI+PP': 25000, PP: 15000, UWI: 8000 }

      effectivenessEvents.push({
        id: `${shipId}-${maint.event_type}-${maint.event_day}`,
        date: dayToDate(maint.event_day),
        type: eventType,
        port: '—',
        fuelBefore: Number(fuelBefore.toFixed(2)),
        fuelAfter: Number(fuelAfter.toFixed(2)),
        fuelImprovementMt: Number(fuelImprovementMt.toFixed(2)),
        improvementPct: Number(improvementPct.toFixed(1)),
        speedLossBefore: Number(slBefore.toFixed(2)),
        speedLossAfter: Number(slAfter.toFixed(2)),
        isAnomaly,
        anomalyReason,
        costUsd: costEstimate[maint.event_type] || 30000,
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
      typeEffectiveness.push({ type, eventCount: events.length, avgFuelImprovementMt: Number(avgFuelImprovement.toFixed(2)), avgImprovementPct: Number(avgImprovement.toFixed(1)), avgCostUsd: Math.round(avgCost), costPerPctImprovement: Number(costPerPct.toFixed(0)), rating })
    }
    typeEffectiveness.sort((a, b) => b.avgImprovementPct - a.avgImprovementPct)

    // Summary
    const totalFuelSavedMt = effectivenessEvents.reduce((s, e) => s + Math.max(0, e.fuelImprovementMt), 0)
    const totalCost = effectivenessEvents.reduce((s, e) => s + e.costUsd, 0)
    const avgImprovementPct = effectivenessEvents.length > 0
      ? effectivenessEvents.reduce((s, e) => s + e.improvementPct, 0) / effectivenessEvents.length
      : 0
    const bestEvent = effectivenessEvents.reduce((b, e) => (e.improvementPct > (b?.improvementPct ?? -Infinity) ? e : b), effectivenessEvents[0])
    const worstEvent = effectivenessEvents.reduce((w, e) => (e.improvementPct < (w?.improvementPct ?? Infinity) ? e : w), effectivenessEvents[0])

    // Optimal timing
    const lastPoint = data[data.length - 1]
    const currentSL = lastPoint && lastPoint.ref_stw > 0 ? ((lastPoint.ref_stw - lastPoint.stw) / lastPoint.ref_stw) * 100 : 0
    const recent = data.slice(-60)
    const rate = recent.length >= 2
      ? (((recent[recent.length - 1].ref_stw > 0 ? ((recent[recent.length - 1].ref_stw - recent[recent.length - 1].stw) / recent[recent.length - 1].ref_stw) * 100 : 0)
        - (recent[0].ref_stw > 0 ? ((recent[0].ref_stw - recent[0].stw) / recent[0].ref_stw) * 100 : 0))
        / (recent[recent.length - 1].noon_day - recent[0].noon_day))
      : 0

    const optimalThreshold = 8
    const daysUntilThreshold = rate > 0 ? Math.max(0, Math.round((optimalThreshold - currentSL) / rate)) : 90
    let recommendedAction: MaintenanceEventType = 'Hull Cleaning'
    if (currentSL >= 12) recommendedAction = 'Hull Cleaning + PP'
    else if (currentSL < 4) recommendedAction = 'Propeller Polishing'

    const baselineFuel = W1_SHIPS.includes(shipId) ? 155 : 92
    const fuelPrice = 620
    const excessFuelCostPerDayUsd = Math.round(baselineFuel * (Math.max(0, currentSL) / 100) * 1.8 * fuelPrice)
    const projectedSavingsUsd = Math.round(baselineFuel * ((typeEffectiveness[0]?.avgImprovementPct || 5) / 100) * 1.8 * fuelPrice * 90)

    const lastDay = lastPoint?.noon_day || 1800
    let urgency: 'LOW' | 'MEDIUM' | 'HIGH' = 'LOW'
    if (currentSL >= 10 || daysUntilThreshold <= 7) urgency = 'HIGH'
    else if (currentSL >= 6 || daysUntilThreshold <= 30) urgency = 'MEDIUM'

    let reasoning: string
    if (urgency === 'HIGH') reasoning = `Speed Loss ${currentSL.toFixed(1)}% 已超過閾值，每日超額成本 $${excessFuelCostPerDayUsd.toLocaleString()}。建議立即安排維修。`
    else if (urgency === 'MEDIUM') reasoning = `Speed Loss ${currentSL.toFixed(1)}%，約 ${daysUntilThreshold} 天後達閾值。建議提前安排。`
    else reasoning = `Speed Loss ${currentSL.toFixed(1)}% 正常範圍，依標準週期維護。`

    const optimalTiming: OptimalMaintenanceTiming = {
      recommendedAction,
      currentSpeedLossPct: Number(currentSL.toFixed(1)),
      degradationRatePerDay: Number(rate.toFixed(4)),
      optimalThresholdPct: optimalThreshold,
      daysUntilThreshold,
      windowStart: dayToDate(lastDay + daysUntilThreshold),
      windowEnd: dayToDate(lastDay + daysUntilThreshold + 14),
      excessFuelCostPerDayUsd,
      projectedSavingsUsd,
      reasoning,
      urgency,
    }

    return {
      vessel: { imo: shipId, name: shipId },
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
    }
  } catch {
    return null
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function buildVesselSummary(
  shipId: string,
  avgConsumption: number,
  rank?: ApiFleetRankingEntry,
  lastMaintDay?: number,
  totalRecords?: number,
): VesselSummary {
  const designSpeed = W1_SHIPS.includes(shipId) ? 22.5 : 21.0
  const speedLossPct = rank?.recent_90d_slip_pct ?? rank?.avg_slip_pct ?? 0
  const rate = rank ? rank.slip_trend / 90 : 0 // slip_trend is 90-day diff

  const urgency: Urgency = speedLossPct >= 14 ? 'HIGH' : speedLossPct >= 10 ? 'MEDIUM' : 'LOW'
  const foulingGrade: FoulingGrade = speedLossPct < 3 ? 'Clean' : speedLossPct < 7 ? 'Light' : speedLossPct < 13 ? 'Moderate' : 'Heavy'

  // Approximate "current day" — 5 years of data from Day 0 ≈ Day 1825
  // The actual last noon_day varies per ship but is roughly in this range
  const APPROX_CURRENT_DAY = 1850
  const maintDay = lastMaintDay || 0
  const daysSinceClean = maintDay > 0 ? Math.max(0, APPROX_CURRENT_DAY - maintDay) : 0

  const baselineFuel = W1_SHIPS.includes(shipId) ? 155 : 92
  const excessFuelCostUsdMtd = Math.round(Math.max(0, speedLossPct) * baselineFuel * 0.018 * 620)

  return {
    imo: shipId,
    name: shipId,
    type: W1_SHIPS.includes(shipId) ? 'W1' : 'W2',
    shipClass: W1_SHIPS.includes(shipId) ? 'W1' : 'W2',
    teuCapacity: 0,
    builtYear: 0,
    flag: '',
    mainEngineModel: '',
    designSpeedKt: designSpeed,
    tradeRoute: W1_SHIPS.includes(shipId) ? 'W1 航線（亞歐）' : 'W2 航線（跨太平洋）',
    status: 'underway',
    currentPort: null,
    destinationPort: null,
    position: { lat: 0, lon: 0, headingDeg: 0, speedKt: 0, courseTrueDeg: 0 },
    speedLossPct: Number(speedLossPct.toFixed(2)),
    avgSlipPct: null,
    slipTrend: null,
    validSlipRecords: null,
    foulingGrade,
    avgSpeedKn: null,
    avgStwKn: null,
    avgRpm: null,
    avgConsumptionMt: avgConsumption || null,
    avgSfoc: null,
    avgLoadPct: null,
    avgWindScale: null,
    avgSeaHeightM: null,
    avgSeaWaterTempC: null,
    avgForeDraftM: null,
    avgAftDraftM: null,
    avgCargoOnBoardMt: null,
    totalRecords: totalRecords || 0,
    totalVoyages: 0,
    dataDayMin: null,
    dataDayMax: null,
    dataSpanDays: null,
    lastDrydockDate: maintDay > 0 ? dayToDate(maintDay) : '—',
    nextDrydockDue: maintDay > 0 ? dayToDate(maintDay + 900) : '—',
    daysSinceHullClean: daysSinceClean,
    daysSinceMaintenance: daysSinceClean,
    daysSincePropPolish: null,
    totalMaintEvents: null,
    lastEventType: null,
    lastHullCleanType: null,
    maintenanceUrgency: urgency,
    maintenanceStatus: urgency === 'HIGH' ? 'needs_request' : 'normal',
    degradationRatePctPerDay: Number(rate.toFixed(4)),
    excessFuelCostUsdMtd,
    nextRecommendedWindow: {
      start: dayToDate(APPROX_CURRENT_DAY + 30),
      end: dayToDate(APPROX_CURRENT_DAY + 60),
    },
  }
}

/** Build VesselSummary directly from the /fleet/summary per_vessel entry — no extra API calls needed. */
function buildVesselSummaryFromSummary(v: ApiFleetSummaryVessel): VesselSummary {
  const shipId = v.vessel_id
  const speedLossPct = v.recent_90d_slip_pct ?? v.avg_slip_pct ?? 0
  const rate = v.slip_trend != null ? v.slip_trend / 90 : 0
  const designSpeed = W1_SHIPS.includes(shipId) ? 22.5 : 21.0

  const urgency: Urgency = v.urgency as Urgency
  const foulingGrade: FoulingGrade =
    speedLossPct < 3 ? 'Clean' : speedLossPct < 7 ? 'Light' : speedLossPct < 13 ? 'Moderate' : 'Heavy'

  const daysSinceHullClean = v.days_since_hull_clean ?? v.days_since_maintenance ?? 0

  // Derive maintenanceStatus from urgency + days since maintenance
  const maintenanceStatus: import('@/types/fleet').MaintenanceStatus =
    urgency === 'HIGH' ? 'needs_request' : 'normal'

  // Convert day numbers to ISO dates
  const lastHullCleanDate = v.last_hull_clean_day != null ? dayToDate(v.last_hull_clean_day) : '—'
  const nextDrydockDue = v.last_hull_clean_day != null ? dayToDate(v.last_hull_clean_day + 900) : '—'
  const windowStart = v.day_range_max != null ? dayToDate(v.day_range_max + 30) : '—'
  const windowEnd   = v.day_range_max != null ? dayToDate(v.day_range_max + 60) : '—'

  return {
    imo: shipId,
    name: shipId,
    type: v.type === 'training' ? (W1_SHIPS.includes(shipId) ? 'W1' : 'W2') : v.type,
    shipClass: v.ship_class || (W1_SHIPS.includes(shipId) ? 'W1' : 'W2'),
    teuCapacity: 0,
    builtYear: 0,
    flag: '',
    mainEngineModel: '',
    designSpeedKt: designSpeed,
    tradeRoute: W1_SHIPS.includes(shipId) ? 'W1 航線（亞歐）' : 'W2 航線（跨太平洋）',
    status: 'underway',
    currentPort: null,
    destinationPort: null,
    position: {
      lat: v.lat,
      lon: v.lon,
      headingDeg: v.heading_deg,
      speedKt: v.speed_kt,
      courseTrueDeg: v.heading_deg,
    },
    // slip
    speedLossPct: Number(speedLossPct.toFixed(2)),
    avgSlipPct: v.avg_slip_pct,
    slipTrend: v.slip_trend,
    validSlipRecords: v.valid_slip_records,
    foulingGrade,
    // performance
    avgSpeedKn: v.avg_speed_kn,
    avgStwKn: v.avg_stw_kn,
    avgRpm: v.avg_rpm,
    avgConsumptionMt: v.avg_consumption_mt,
    avgSfoc: v.avg_sfoc,
    avgLoadPct: v.avg_load_pct,
    // environment
    avgWindScale: v.avg_wind_scale,
    avgSeaHeightM: v.avg_sea_height_m,
    avgSeaWaterTempC: v.avg_sea_water_temp_c,
    // loading
    avgForeDraftM: v.avg_fore_draft_m,
    avgAftDraftM: v.avg_aft_draft_m,
    avgCargoOnBoardMt: v.avg_cargo_on_board_mt,
    // voyage
    totalRecords: v.total_records,
    totalVoyages: v.total_voyages,
    dataDayMin: v.day_range_min,
    dataDayMax: v.day_range_max,
    dataSpanDays: v.data_span_days,
    // maintenance
    lastDrydockDate: lastHullCleanDate,
    nextDrydockDue,
    daysSinceHullClean,
    daysSinceMaintenance: v.days_since_maintenance,
    daysSincePropPolish: v.days_since_prop_polish,
    totalMaintEvents: v.total_maint_events,
    lastEventType: v.last_event_type,
    lastHullCleanType: v.last_hull_clean_type,
    maintenanceUrgency: urgency,
    maintenanceStatus,
    // cost
    degradationRatePctPerDay: Number(rate.toFixed(4)),
    excessFuelCostUsdMtd: v.excess_fuel_cost_usd_per_day,
    nextRecommendedWindow: { start: windowStart, end: windowEnd },
  }
}
