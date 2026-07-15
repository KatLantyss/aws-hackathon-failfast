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
  fetchApiSpeedLossAttribution,
  type ApiSpeedLossAttribution,
  fetchApiVessels,
  fetchApiVesselDetail,
  fetchApiSpeedLoss,
  fetchApiMaintenanceEvents,
  fetchApiFleetRanking,
  fetchApiFleetSummary,
  fetchApiNoonReports,
  fetchApiMaintenanceRecommendation,
  type ApiFocTimelinePoint,
  type ApiStwTimelinePoint,
  type ApiMaintenanceEvent,
  type ApiFleetRankingEntry,
  type ApiFleetSummaryVessel,
} from '@/api/client'

// ─── Constants ────────────────────────────────────────────────────────────────

const W1_SHIPS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S21']
const W2_SHIPS = ['S9', 'S10', 'S11', 'S12', 'S22', 'S23']
const ALL_SHIPS = [...W1_SHIPS, ...W2_SHIPS]


// Maintenance event type mapping.
// UWI (pure underwater inspection) does no cleaning or polishing — mirrors
// backend handler.py's own physical_intervention / category logic for
// speed-loss-attribution, where plain 'UWI' is the only event_type that is
// NOT a physical intervention and gets category 'inspection_only'. It must
// never be mapped to hull_cleaning/propeller_polishing here, or downstream
// consumers (SpeedLoss.vue's cleaningDays cycle-boundary filter,
// fetchRealMaintenanceCorrelation's effectiveness scoring below) will treat
// a no-op inspection as if it restored performance.
const EVENT_TYPE_MAP: Record<string, SpeedLossEvent['type']> = {
  PP: 'propeller_polishing',
  'UWI+PP': 'propeller_polishing',
  UWC: 'hull_cleaning',
  'UWC+PP': 'hull_cleaning',
  DD: 'drydock',
  UWI: 'inspection',
}
const EVENT_LABEL_MAP: Record<string, string> = {
  PP: '螺旋槳拋光',
  'UWI+PP': '水下檢查+拋光',
  UWC: '船殼清洗',
  'UWC+PP': '清洗+拋光',
  DD: '進塢',
  UWI: '水下檢查',
}
// No 'UWI' entry: plain inspections are excluded before this map is
// consulted (see the `continue` at the top of the loop in
// fetchRealMaintenanceCorrelation) rather than mislabeled as a real
// intervention type.
const CORRELATION_TYPE_MAP: Record<string, MaintenanceEventType> = {
  DD: 'Hull Cleaning + PP',
  'UWC+PP': 'Hull Cleaning + PP',
  UWC: 'Hull Cleaning',
  'UWI+PP': 'Propeller Polishing',
  PP: 'Propeller Polishing',
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
    // Use fleet/summary (single call, all fields pre-computed) instead of
    // assembling from 3 separate API calls with many null fields.
    const summary = await fetchApiFleetSummary()
    const vessel = summary.per_vessel.find((v) => v.vessel_id === shipId)
    if (vessel) {
      return buildVesselSummaryFromSummary(vessel)
    }
    // Fallback: vessel not in fleet/summary (shouldn't happen for S1-S23)
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

    // Use foc_timeline as primary source (competition-spec FOC-based speed loss).
    // Fall back to stw_timeline if foc_timeline is empty.
    const focData = slResp.foc_timeline ?? []
    const stwData = slResp.stw_timeline ?? []

    let reports: NoonReportEntry[]

    if (focData.length > 0) {
      reports = focData.map((p) => ({
        day: p.noon_day,
        lat: 0,
        lon: 0,
        observedSpeedKt: p.stw ?? 0,
        correctedSpeedKt: 0,
        speedLossPct: p.speed_loss_pct,
        fuelConsumptionMt: p.daily_foc_vlsfo,
        beaufort: p.wind_scale,
        seaState: p.wind_scale,
        draftFwd: 0,
        draftAft: 0,
        loadCondition: p.load_condition,
      }))
    } else if (stwData.length > 0) {
      reports = stwData.map((p) => ({
        day: p.noon_day,
        lat: 0,
        lon: 0,
        observedSpeedKt: p.stw,
        correctedSpeedKt: p.ref_stw,
        speedLossPct: p.speed_loss_pct,
        fuelConsumptionMt: 0,
        beaufort: p.wind_scale,
        seaState: p.wind_scale,
        draftFwd: 0,
        draftAft: 0,
        loadCondition: p.load_condition,
      }))
    } else {
      reports = []
    }

    const events: SpeedLossEvent[] = maintResp.events.map((e) => ({
      day: e.event_day,
      type: EVENT_TYPE_MAP[e.event_type] || 'hull_cleaning',
      label: EVENT_LABEL_MAP[e.event_type] || e.event_type,
    }))

    return {
      vessel: { imo: shipId, name: shipId, type: W1_SHIPS.includes(shipId) ? 'W1' : 'W2' },
      events,
      reports,
    }
  } catch {
    return null
  }
}

export async function fetchRealMaintenanceRecommendation(shipId: string): Promise<MaintenanceRecommendation | null> {
  try {
    const [rec, vessel] = await Promise.all([
      fetchApiMaintenanceRecommendation(shipId),
      fetchRealVesselSummary(shipId),
    ])
    if (!vessel) return null

    const curve: CostBenefitPoint[] = rec.curve.map((p) => ({
      deferralDays: p.deferral_days,
      cumulativeExcessFuelCostUsd: p.cumulative_excess_fuel_cost_usd,
    }))

    // Confidence reflects how much real data backs the degradation rate —
    // not a guess: it needs a full prior 90-day window to compute a rate at all.
    const confidence: Confidence =
      rec.avg_consumption_mt == null ? 'low' : rec.degradation_rate_pct_per_day !== 0 ? 'high' : 'medium'

    // "Savings" = the real cumulative excess fuel cost projected over the
    // curve's full deferral window if maintenance is NOT done now.
    const estimatedSavingUsd = curve.length ? curve[curve.length - 1].cumulativeExcessFuelCostUsd : 0

    return {
      action: rec.recommended_type === 'DD' ? 'drydock' : 'hull_cleaning',
      windowStartDay: vessel.nextRecommendedWindow.startDay,
      windowEndDay: vessel.nextRecommendedWindow.endDay,
      estimatedSavingUsd,
      confidence,
      reasoning: `${rec.reason}（Avg ME Slip ${rec.avg_me_slip_pct?.toFixed(1) ?? '—'}%，距上次養護 ${rec.days_since_maintenance} 天）。`,
      dataLimitations: rec.avg_consumption_mt == null
        ? ['此船油耗資料不足，無法計算可靠的成本效益曲線，以下為概略估計。']
        : [],
      curve,
    }
  } catch {
    return null
  }
}

export async function fetchRealFuelAttribution(shipId: string): Promise<import('@/types/fleet').FuelAttributionResponse | null> {
  try {
    const [attribution, vessel] = await Promise.all([
      fetchApiSpeedLossAttribution(shipId),
      fetchRealVesselSummary(shipId),
    ])
    if (!vessel) return null
    return buildFuelAttributionFromBackend(attribution, vessel)
  } catch {
    return null
  }
}

function buildFuelAttributionFromBackend(
  source: ApiSpeedLossAttribution,
  vessel: VesselSummary,
): import('@/types/fleet').FuelAttributionResponse {
  const actualFuelMt = vessel.avgConsumptionMt ?? 0
  const baselineFuelMt = actualFuelMt / (1 + Math.max(0, vessel.speedLossPct) * 0.018)
  const toImpactMt = (slipDelta: number) => Math.max(0, actualFuelMt * Math.abs(slipDelta) * 0.018)
  const categoryImpact = (category: string) => source.event_attributions
    .filter((event) => event.category === category && event.physical_intervention && event.slip_delta_pct != null)
    .map((event) => toImpactMt(event.slip_delta_pct))
    .reduce((sum, impact) => sum + impact, 0)
  const weatherImpact = source.weather_timeline.length
    ? actualFuelMt * (source.weather_timeline.reduce((sum, point) => sum + Math.abs(point.diff_stw_sog), 0) / source.weather_timeline.length) * 0.003
    : 0
  const hullImpact = categoryImpact('hull') + categoryImpact('hull+propeller') / 2
  const propellerImpact = categoryImpact('propeller') + categoryImpact('hull+propeller') / 2
  const derivedImpact = Math.max(0, actualFuelMt - baselineFuelMt)
  const knownImpact = hullImpact + propellerImpact + weatherImpact
  const engineImpact = Math.max(0, derivedImpact - knownImpact)
  const confidence: import('@/types/fleet').Confidence = source.event_attributions.some((event) => event.slip_delta_pct != null)
    ? 'medium'
    : 'low'

  return {
    baselineFuelMt,
    actualFuelMt,
    attribution: [
      { factor: 'weather', impactMt: Number(weatherImpact.toFixed(2)), label: '天候／海流代理值' },
      { factor: 'hull_fouling', impactMt: Number(hullImpact.toFixed(2)), label: '船殼維護前後差異' },
      { factor: 'propeller_fouling', impactMt: Number(propellerImpact.toFixed(2)), label: '螺旋槳維護前後差異' },
      { factor: 'engine_degradation', impactMt: Number(engineImpact.toFixed(2)), label: '未歸因之效能差異' },
    ],
    confidence,
    timeSeries: source.weather_timeline.map((point) => ({
      date: `Day ${point.noon_day}`,
      weather: point.diff_stw_sog,
      hull_fouling: 0,
      propeller_fouling: 0,
      engine_degradation: 0,
    })),
  }
}

export async function fetchRealMaintenanceCorrelation(shipId: string): Promise<MaintenanceCorrelationResponse | null> {
  try {
    const [slResp, maintResp, detail] = await Promise.all([
      fetchApiSpeedLoss(shipId),
      fetchApiMaintenanceEvents(shipId),
      fetchApiVesselDetail(shipId),
    ])
    // This vessel's own real average fuel consumption (mean ME_CONSUMPTION) —
    // not a guessed per-class baseline.
    const avgConsumptionMt = detail.avg_consumption ?? null

    // Use foc_timeline (primary) or stw_timeline (fallback) — both now have speed_loss_pct directly
    const focData = slResp.foc_timeline ?? []
    const stwData = slResp.stw_timeline ?? []
    const primaryData = focData.length > 0 ? focData : stwData

    // Build timeline (sample every 5th point to reduce density)
    const timeline: PerformanceTimelinePoint[] = primaryData
      .filter((_, i) => i % 5 === 0)
      .map((p) => {
        return {
          day: p.noon_day,
          fuelConsumptionMt: 'daily_foc_vlsfo' in p ? (p as typeof focData[0]).daily_foc_vlsfo : 0,
          speedLossPct: Number(p.speed_loss_pct.toFixed(2)),
        }
      })

    // Compute before/after for each maintenance event
    const WINDOW_DAYS = 14
    const effectivenessEvents: MaintenanceEffectivenessEvent[] = []

    for (const maint of maintResp.events) {
      // Pure inspection (UWI) performs no physical work — mirrors backend's
      // physical_intervention=false / category='inspection_only' for this
      // exact event_type. Scoring it here would misrepresent a no-op as a
      // real fuel/speed-loss improvement, which the dataset's own event
      // semantics explicitly rule out.
      if (maint.event_type === 'UWI') continue

      const before = primaryData.filter(
        (p) => p.noon_day >= maint.event_day - WINDOW_DAYS && p.noon_day < maint.event_day
      )
      const after = primaryData.filter(
        (p) => p.noon_day > maint.event_day && p.noon_day <= maint.event_day + WINDOW_DAYS
      )

      if (before.length < 3 || after.length < 3 || avgConsumptionMt == null) continue

      const slBefore = before.reduce((s, p) => s + p.speed_loss_pct, 0) / before.length
      const slAfter = after.reduce((s, p) => s + p.speed_loss_pct, 0) / after.length

      // Theoretical fuel impact (cubic-law approximation: 1% slip ≈ 1.8% fuel increase),
      // scaled off this vessel's own real average consumption.
      const fuelBefore = avgConsumptionMt * (1 + Math.max(0, slBefore) / 100 * 1.8)
      const fuelAfter = avgConsumptionMt * (1 + Math.max(0, slAfter) / 100 * 1.8)
      const fuelImprovementMt = fuelBefore - fuelAfter
      const improvementPct = fuelBefore > 0 ? (fuelImprovementMt / fuelBefore) * 100 : 0

      const eventType = CORRELATION_TYPE_MAP[maint.event_type] || 'Hull Cleaning'

      // Anomaly detection
      let isAnomaly = false
      let anomalyReason: string | null = null
      if (maint.event_type === 'DD' && improvementPct < 2) {
        isAnomaly = true
        anomalyReason = '進塢後 Speed Loss 改善不明顯 (<2%)，建議確認塗裝品質。'
      } else if (maint.event_type === 'PP' && improvementPct > 18) {
        isAnomaly = true
        anomalyReason = '螺旋槳拋光改善幅度異常高 (>18%)，可能有其他因素或量測誤差。'
      } else if (improvementPct < 0) {
        isAnomaly = true
        anomalyReason = '養護後效能反而下降，可能施工品質不佳或環境因素影響。'
      }

      effectivenessEvents.push({
        id: `${shipId}-${maint.event_type}-${maint.event_day}`,
        day: maint.event_day,
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
      let rating = 1
      if (avgImprovement >= 10) rating = 5
      else if (avgImprovement >= 6) rating = 4
      else if (avgImprovement >= 3) rating = 3
      else if (avgImprovement >= 1) rating = 2
      typeEffectiveness.push({ type, eventCount: events.length, avgFuelImprovementMt: Number(avgFuelImprovement.toFixed(2)), avgImprovementPct: Number(avgImprovement.toFixed(1)), rating })
    }
    typeEffectiveness.sort((a, b) => b.avgImprovementPct - a.avgImprovementPct)

    // Summary
    const totalFuelSavedMt = effectivenessEvents.reduce((s, e) => s + Math.max(0, e.fuelImprovementMt), 0)
    const avgImprovementPct = effectivenessEvents.length > 0
      ? effectivenessEvents.reduce((s, e) => s + e.improvementPct, 0) / effectivenessEvents.length
      : 0
    const bestEvent = effectivenessEvents.reduce((b, e) => (e.improvementPct > (b?.improvementPct ?? -Infinity) ? e : b), effectivenessEvents[0])
    const worstEvent = effectivenessEvents.reduce((w, e) => (e.improvementPct < (w?.improvementPct ?? Infinity) ? e : w), effectivenessEvents[0])

    // Optimal timing — compute from most recent data
    const lastPoint = primaryData[primaryData.length - 1]

    // "Current" SL + degradation rate both come from a trailing window (last
    // 60 raw points), not a single last-day point — per-day speed_loss_pct is
    // extremely noisy (a single maneuvering/idle/bad-weather day can spike
    // past 60% even on a healthy hull), so averaging is required to land near
    // the backend's own filtered foc_summary.avg_speed_loss_pct.
    const recent = primaryData.slice(-60)
    const currentSL = recent.length > 0
      ? recent.reduce((s, p) => s + p.speed_loss_pct, 0) / recent.length
      : lastPoint?.speed_loss_pct ?? 0

    let rate = 0
    if (recent.length >= 2) {
      const slStart = recent[0].speed_loss_pct
      const slEnd = recent[recent.length - 1].speed_loss_pct
      const daySpan = recent[recent.length - 1].noon_day - recent[0].noon_day
      rate = daySpan > 0 ? (slEnd - slStart) / daySpan : 0
    }

    const optimalThreshold = 8
    const daysUntilThreshold = rate > 0 ? Math.max(0, Math.round((optimalThreshold - currentSL) / rate)) : 90
    let recommendedAction: MaintenanceEventType = 'Hull Cleaning'
    if (currentSL >= 12) recommendedAction = 'Hull Cleaning + PP'
    else if (currentSL < 4) recommendedAction = 'Propeller Polishing'

    const fuelPrice = 620
    const excessFuelCostPerDayUsd = avgConsumptionMt != null
      ? Math.round(avgConsumptionMt * (Math.max(0, currentSL) / 100) * 1.8 * fuelPrice)
      : 0
    const projectedSavingsUsd = avgConsumptionMt != null
      ? Math.round(avgConsumptionMt * ((typeEffectiveness[0]?.avgImprovementPct ?? 0) / 100) * 1.8 * fuelPrice * 90)
      : 0

    const lastDay = lastPoint?.noon_day ?? 1800
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
      windowStartDay: lastDay + daysUntilThreshold,
      windowEndDay: lastDay + daysUntilThreshold + 14,
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
  const speedLossPct = rank?.recent_90d_slip_pct ?? rank?.avg_slip_pct ?? 0
  const rate = rank ? rank.slip_trend / 90 : 0 // slip_trend is 90-day diff

  const urgency: Urgency = speedLossPct >= 14 ? 'HIGH' : speedLossPct >= 10 ? 'MEDIUM' : 'LOW'
  const foulingGrade: FoulingGrade = speedLossPct < 3 ? 'Clean' : speedLossPct < 7 ? 'Light' : speedLossPct < 13 ? 'Moderate' : 'Heavy'

  // Approximate "current day" — 5 years of data from Day 0 ≈ Day 1825
  // The actual last noon_day varies per ship but is roughly in this range
  const APPROX_CURRENT_DAY = 1850
  const maintDay = lastMaintDay || 0
  const daysSinceClean = maintDay > 0 ? Math.max(0, APPROX_CURRENT_DAY - maintDay) : 0

  // Uses this vessel's own real avg consumption, not a guessed per-class baseline.
  const excessFuelCostUsdMtd = avgConsumption ? Math.round(Math.max(0, speedLossPct) * avgConsumption * 0.018 * 620) : 0

  return {
    imo: shipId,
    name: shipId,
    type: W1_SHIPS.includes(shipId) ? 'W1' : 'W2',
    shipClass: W1_SHIPS.includes(shipId) ? 'W1' : 'W2',
    teuCapacity: 0,
    builtYear: 0,
    flag: '',
    mainEngineModel: '',
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
    lastDrydockDay: maintDay > 0 ? maintDay : null,
    nextDrydockDueDay: maintDay > 0 ? maintDay + 900 : null,
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
      startDay: APPROX_CURRENT_DAY + 30,
      endDay: APPROX_CURRENT_DAY + 60,
    },
  }
}

/** Build VesselSummary directly from the /fleet/summary per_vessel entry — no extra API calls needed. */
function buildVesselSummaryFromSummary(v: ApiFleetSummaryVessel): VesselSummary {
  const shipId = v.vessel_id
  const speedLossPct = v.recent_90d_slip_pct ?? v.avg_slip_pct ?? 0
  const rate = v.slip_trend != null ? v.slip_trend / 90 : 0

  const urgency: Urgency = v.urgency as Urgency
  const foulingGrade: FoulingGrade =
    speedLossPct < 3 ? 'Clean' : speedLossPct < 7 ? 'Light' : speedLossPct < 13 ? 'Moderate' : 'Heavy'

  const daysSinceHullClean = v.days_since_hull_clean ?? v.days_since_maintenance ?? 0

  // Derive maintenanceStatus from urgency + days since maintenance
  const maintenanceStatus: import('@/types/fleet').MaintenanceStatus =
    urgency === 'HIGH' ? 'needs_request' : 'normal'

  const lastHullCleanDay = v.last_hull_clean_day ?? null
  const nextDrydockDueDay = v.last_hull_clean_day != null ? v.last_hull_clean_day + 900 : null
  const windowStartDay = v.day_range_max != null ? v.day_range_max + 30 : 0
  const windowEndDay   = v.day_range_max != null ? v.day_range_max + 60 : 0

  return {
    imo: shipId,
    name: shipId,
    type: v.type === 'training' ? (W1_SHIPS.includes(shipId) ? 'W1' : 'W2') : v.type,
    shipClass: v.ship_class || (W1_SHIPS.includes(shipId) ? 'W1' : 'W2'),
    teuCapacity: 0,
    builtYear: 0,
    flag: '',
    mainEngineModel: '',
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
    lastDrydockDay: lastHullCleanDay,
    nextDrydockDueDay,
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
    nextRecommendedWindow: { startDay: windowStartDay, endDay: windowEndDay },
  }
}
