/**
 * Real data adapter — loads speed_loss_results.csv and maintenance.csv
 * and exposes them through the same interface as the mock API.
 *
 * Ship mapping: S1-S23 are displayed as-is (competition dataset ships).
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

// -------------------------------------------------------------------
// Raw CSV data will be loaded at build time via Vite's ?raw import
// -------------------------------------------------------------------
import speedLossRaw from '../../speed_loss_results.csv?raw'
import maintenanceRaw from '../../yangming-aws-summit-hackathon/maintenance.csv?raw'
import maintenanceRecsRaw from '../../maintenance_recommendations.csv?raw'

// -------------------------------------------------------------------
// CSV parsing helpers
// -------------------------------------------------------------------
function parseCSV(raw: string): Record<string, string>[] {
  const lines = raw.trim().split('\n')
  const headers = lines[0].split(',').map((h) => h.trim())
  return lines.slice(1).map((line) => {
    const values = line.split(',')
    const obj: Record<string, string> = {}
    headers.forEach((h, i) => {
      obj[h] = (values[i] || '').trim()
    })
    return obj
  })
}

// -------------------------------------------------------------------
// Parsed datasets
// -------------------------------------------------------------------
const speedLossRows = parseCSV(speedLossRaw)
const maintenanceRows = parseCSV(maintenanceRaw)
const maintenanceRecs = parseCSV(maintenanceRecsRaw)

// Ship type mapping from README
const W1_SHIPS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S21']
const W2_SHIPS = ['S9', 'S10', 'S11', 'S12', 'S22', 'S23']
const ALL_SHIPS = [...W1_SHIPS, ...W2_SHIPS]

// Mock position data for real ships — placed along YM's main trade routes
// W1 ships: Asia-Europe route (FE3-like)
// W2 ships: Trans-Pacific / Intra-Asia
const SHIP_POSITIONS: Record<string, { lat: number; lon: number; headingDeg: number; speedKt: number; status: 'underway' | 'moored' | 'anchored'; currentPort: string | null; destinationPort: string | null }> = {
  S1:  { lat: 22.28, lon: 114.17, headingDeg: 210, speedKt: 19.2, status: 'underway', currentPort: null, destinationPort: 'Singapore' },
  S2:  { lat: 1.26, lon: 103.84, headingDeg: 0, speedKt: 0, status: 'moored', currentPort: 'Singapore', destinationPort: null },
  S3:  { lat: 13.45, lon: 56.32, headingDeg: 285, speedKt: 17.8, status: 'underway', currentPort: null, destinationPort: 'Suez Canal' },
  S4:  { lat: 51.89, lon: 4.48, headingDeg: 0, speedKt: 0, status: 'moored', currentPort: 'Rotterdam', destinationPort: null },
  S5:  { lat: 35.32, lon: 29.78, headingDeg: 105, speedKt: 18.5, status: 'underway', currentPort: null, destinationPort: 'Port Said' },
  S6:  { lat: 6.93, lon: 79.85, headingDeg: 70, speedKt: 20.1, status: 'underway', currentPort: null, destinationPort: 'Colombo' },
  S7:  { lat: 25.28, lon: 55.32, headingDeg: 0, speedKt: 0, status: 'anchored', currentPort: null, destinationPort: 'Jebel Ali' },
  S8:  { lat: 29.87, lon: 121.55, headingDeg: 180, speedKt: 16.9, status: 'underway', currentPort: null, destinationPort: 'Ningbo' },
  S9:  { lat: 34.05, lon: -118.25, headingDeg: 0, speedKt: 0, status: 'moored', currentPort: 'Los Angeles', destinationPort: null },
  S10: { lat: 33.73, lon: -140.22, headingDeg: 90, speedKt: 19.7, status: 'underway', currentPort: null, destinationPort: 'Long Beach' },
  S11: { lat: 22.62, lon: 120.30, headingDeg: 0, speedKt: 0, status: 'moored', currentPort: 'Kaohsiung', destinationPort: null },
  S12: { lat: 37.47, lon: -165.88, headingDeg: 72, speedKt: 18.3, status: 'underway', currentPort: null, destinationPort: 'Vancouver' },
  S21: { lat: 10.24, lon: 75.82, headingDeg: 255, speedKt: 19.4, status: 'underway', currentPort: null, destinationPort: 'Fujairah' },
  S22: { lat: 25.02, lon: 170.54, headingDeg: 55, speedKt: 17.6, status: 'underway', currentPort: null, destinationPort: 'Yokohama' },
  S23: { lat: 31.23, lon: 121.47, headingDeg: 0, speedKt: 0, status: 'anchored', currentPort: null, destinationPort: 'Shanghai' },
}

// Ship display names removed — using competition ship IDs (S1-S23) directly

// Maintenance event type to SpeedLossEvent type mapping
const EVENT_TYPE_MAP: Record<string, SpeedLossEvent['type']> = {
  PP: 'propeller_polishing',
  'UWI+PP': 'propeller_polishing',
  UWC: 'hull_cleaning',
  'UWC+PP': 'hull_cleaning',
  DD: 'drydock',
  UWI: 'hull_cleaning', // inspection only, but show as marker
}

const EVENT_LABEL_MAP: Record<string, string> = {
  PP: '螺旋槳拋光',
  'UWI+PP': '水下檢查+拋光',
  UWC: '船殼清洗',
  'UWC+PP': '清洗+拋光',
  DD: '進塢',
  UWI: '水下檢查',
}

// Base date: Day 0 = 2020-01-01 (arbitrary, for display purposes)
const BASE_DATE = new Date('2020-01-01')

function dayToDate(day: number): string {
  const d = new Date(BASE_DATE)
  d.setDate(d.getDate() + day)
  return d.toISOString().slice(0, 10)
}

// -------------------------------------------------------------------
// Build per-ship data
// -------------------------------------------------------------------
interface ShipSpeedLossRow {
  day: number
  speedLossPct: number
  stwExpected: number
  stwActual: number
  eventType?: string
}

const shipDataCache = new Map<string, ShipSpeedLossRow[]>()

function getShipData(shipId: string): ShipSpeedLossRow[] {
  if (shipDataCache.has(shipId)) return shipDataCache.get(shipId)!

  const rows = speedLossRows
    .filter((r) => r.ship_id === shipId)
    .map((r) => ({
      day: Number(r.NOON_UTC),
      speedLossPct: Number(r.speed_loss_pct),
      stwExpected: Number(r.stw_expected),
      stwActual: Number(r.stw_actual),
      eventType: r.event_type || undefined,
    }))
    .filter((r) => !isNaN(r.day) && !isNaN(r.speedLossPct))
    // Filter extreme outliers for display
    .filter((r) => r.speedLossPct > -30 && r.speedLossPct < 50)
    .sort((a, b) => a.day - b.day)

  shipDataCache.set(shipId, rows)
  return rows
}

function getMaintenanceEvents(shipId: string): SpeedLossEvent[] {
  return maintenanceRows
    .filter((r) => r.ship_id === shipId)
    .map((r) => ({
      date: dayToDate(Number(r.event_day)),
      type: EVENT_TYPE_MAP[r.event_type] || 'hull_cleaning',
      label: EVENT_LABEL_MAP[r.event_type] || r.event_type,
    }))
    .sort((a, b) => (a.date < b.date ? -1 : 1))
}

// -------------------------------------------------------------------
// Public API (same shape as mock/api.ts)
// -------------------------------------------------------------------

export function getRealShipList(): string[] {
  return ALL_SHIPS
}

export async function fetchRealSpeedLoss(shipId: string): Promise<SpeedLossSeries | null> {
  const rows = getShipData(shipId)
  if (rows.length === 0) return null

  const shipType = W1_SHIPS.includes(shipId) ? 'W1 Container' : 'W2 Container'
  const designSpeed = W1_SHIPS.includes(shipId) ? 22.5 : 21.0

  const reports: NoonReportEntry[] = rows.map((r) => ({
    date: dayToDate(r.day),
    lat: 0,
    lon: 0,
    observedSpeedKt: r.stwActual || 0,
    correctedSpeedKt: r.stwExpected || 0,
    speedLossPct: r.speedLossPct,
    fuelConsumptionMt: 0, // not available from speed_loss calc
    beaufort: 0,
    seaState: 0,
    draftFwd: 0,
    draftAft: 0,
    loadCondition: 'laden',
    isAnomaly: r.speedLossPct > 15,
    anomalyReason: r.speedLossPct > 15 ? '效能異常偏高' : null,
  }))

  const events = getMaintenanceEvents(shipId)

  return {
    vessel: { imo: shipId, name: shipId, type: shipType },
    cleanBaseline: { speedKnots: designSpeed, source: 'post_maintenance' },
    events,
    reports,
  }
}

export async function fetchRealVesselSummary(shipId: string): Promise<VesselSummary | null> {
  const rows = getShipData(shipId)
  if (rows.length === 0) return null

  const lastRow = rows[rows.length - 1]
  const designSpeed = W1_SHIPS.includes(shipId) ? 22.5 : 21.0

  // Calculate degradation rate (last 60 days)
  const recent = rows.slice(-60)
  const rate = recent.length >= 2
    ? (recent[recent.length - 1].speedLossPct - recent[0].speedLossPct) / (recent[recent.length - 1].day - recent[0].day)
    : 0

  const speedLossPct = lastRow.speedLossPct
  const urgency: Urgency = speedLossPct >= 8 ? 'HIGH' : speedLossPct >= 5 ? 'MEDIUM' : 'LOW'
  const foulingGrade: FoulingGrade = speedLossPct < 3 ? 'Clean' : speedLossPct < 7 ? 'Light' : speedLossPct < 13 ? 'Moderate' : 'Heavy'

  // Find last maintenance
  const shipMaint = maintenanceRows.filter((r) => r.ship_id === shipId).map((r) => Number(r.event_day)).sort((a, b) => b - a)
  const lastMaintDay = shipMaint[0] || 0
  const daysSinceClean = lastRow.day - lastMaintDay

  const pos = SHIP_POSITIONS[shipId] || { lat: 22.6, lon: 120.3, headingDeg: 180, speedKt: 18, status: 'underway' as const, currentPort: null, destinationPort: null }

  return {
    imo: shipId,
    name: shipId, // 競賽匿名代號，直接顯示 S1, S2...
    type: W1_SHIPS.includes(shipId) ? 'W1' : 'W2',
    teuCapacity: 0, // 競賽未提供
    builtYear: 0,   // 競賽未提供
    flag: '',       // 競賽未提供
    mainEngineModel: '', // 競賽未提供
    designSpeedKt: designSpeed,
    tradeRoute: W1_SHIPS.includes(shipId) ? 'W1 航線' : 'W2 航線',
    status: pos.status,
    currentPort: pos.currentPort,
    destinationPort: pos.destinationPort,
    position: { lat: pos.lat, lon: pos.lon, headingDeg: pos.headingDeg, speedKt: pos.speedKt, courseTrueDeg: pos.headingDeg },
    speedLossPct: Number(speedLossPct.toFixed(2)),
    foulingGrade,
    lastDrydockDate: dayToDate(lastMaintDay),
    nextDrydockDue: dayToDate(lastMaintDay + 900),
    daysSinceHullClean: daysSinceClean,
    maintenanceUrgency: urgency,
    degradationRatePctPerDay: Number(rate.toFixed(4)),
    excessFuelCostUsdMtd: Math.round(Math.max(0, speedLossPct) * 620 * 0.5 * 30),
    nextRecommendedWindow: {
      start: dayToDate(lastRow.day + 30),
      end: dayToDate(lastRow.day + 60),
    },
  }
}

export async function fetchRealFleetKpis(): Promise<FleetKpis> {
  const summaries = await Promise.all(ALL_SHIPS.map((s) => fetchRealVesselSummary(s)))
  const valid = summaries.filter((s): s is VesselSummary => s !== null)

  return {
    totalVessels: valid.length,
    underway: valid.length, // all "underway" since we don't have live AIS
    inPort: 0,
    pendingMaintenance: valid.filter((s) => s.maintenanceUrgency !== 'LOW').length,
    monthlyExcessFuelCostUsd: valid.reduce((sum, s) => sum + s.excessFuelCostUsdMtd, 0),
  }
}

export async function fetchRealFleetVessels(): Promise<VesselSummary[]> {
  const summaries = await Promise.all(ALL_SHIPS.map((s) => fetchRealVesselSummary(s)))
  return summaries.filter((s): s is VesselSummary => s !== null)
}

export async function fetchRealMaintenanceRecommendation(shipId: string): Promise<MaintenanceRecommendation | null> {
  const vessel = await fetchRealVesselSummary(shipId)
  if (!vessel) return null

  const recs = maintenanceRecs.filter((r) => r.ship_id === shipId)
  const latestRec = recs[recs.length - 1]

  const rate = vessel.degradationRatePctPerDay
  const speedLossPct = vessel.speedLossPct

  // Generate cost-benefit curve
  const baselineFuelMt = W1_SHIPS.includes(shipId) ? 155 : 92
  const fuelPrice = 620
  const cleaningCost = 30000

  const curve: CostBenefitPoint[] = Array.from({ length: 91 }, (_, i) => {
    const projectedLoss = Math.max(0, speedLossPct + rate * i)
    const excessFuelPerDay = baselineFuelMt * (projectedLoss / 100) * 1.8
    return {
      deferralDays: i,
      cumulativeExcessFuelCostUsd: Math.round(excessFuelPerDay * fuelPrice * i * 0.55),
      opportunityCostUsd: Math.round(cleaningCost * (1 - i / 220)),
    }
  })

  const confidence: Confidence = recs.length >= 3 ? 'high' : recs.length >= 1 ? 'medium' : 'low'

  const action = latestRec?.recommended_action || 'PP'
  const reasoning = latestRec
    ? `Speed Loss 平均 ${Number(latestRec.avg_speed_loss).toFixed(1)}%，趨勢上升中，建議安排 ${EVENT_LABEL_MAP[action] || action}。`
    : `船體污損增長速率 ${(rate * 30).toFixed(2)}%/月，建議定期監控。`

  return {
    action: action === 'DD' ? 'drydock' : action === 'UWC+PP' || action === 'UWC' ? 'hull_cleaning' : 'propeller_polishing',
    windowStart: vessel.nextRecommendedWindow.start,
    windowEnd: vessel.nextRecommendedWindow.end,
    estimatedSavingUsd: Math.round(curve[60]?.cumulativeExcessFuelCostUsd || 50000),
    confidence,
    reasoning,
    dataLimitations: recs.length < 3 ? ['歷史養護事件樣本有限，建議持續監控。'] : [],
    curve,
  }
}

// -------------------------------------------------------------------
// Maintenance-Performance Correlation (Real Data)
// -------------------------------------------------------------------

// Map competition event types to our frontend display types
const CORRELATION_TYPE_MAP: Record<string, MaintenanceEventType> = {
  DD: 'Hull Cleaning + PP', // DD is full drydock - maps to most comprehensive
  'UWC+PP': 'Hull Cleaning + PP',
  UWC: 'Hull Cleaning',
  'UWI+PP': 'Propeller Polishing', // Inspection + Polish
  PP: 'Propeller Polishing',
  UWI: 'Propeller Polishing', // Inspection only, minimal intervention
}

export async function fetchRealMaintenanceCorrelation(shipId: string): Promise<MaintenanceCorrelationResponse | null> {
  const rows = getShipData(shipId)
  if (rows.length === 0) return null

  const vessel = await fetchRealVesselSummary(shipId)
  if (!vessel) return null

  const baselineFuelMt = W1_SHIPS.includes(shipId) ? 155 : 92
  const fuelPrice = 620

  // Build performance timeline from speed loss data
  // Estimate fuel from speed loss: fuel = baseline * (1 + speedLoss/100 * 1.8)
  const timeline: PerformanceTimelinePoint[] = rows
    .filter((_, i) => i % 3 === 0) // downsample for chart performance
    .map((r) => ({
      date: dayToDate(r.day),
      fuelConsumptionMt: Number((baselineFuelMt * (1 + Math.max(0, r.speedLossPct) / 100 * 1.8)).toFixed(2)),
      speedLossPct: Number(r.speedLossPct.toFixed(2)),
    }))

  // Get maintenance events for this ship
  const shipMaintenance = maintenanceRows
    .filter((r) => r.ship_id === shipId)
    .map((r) => ({
      eventDay: Number(r.event_day),
      eventType: r.event_type,
      propellerCondition: r.propeller_condition || '',
      hullFoulingType: r.hull_fouling_type || '',
      hullCoatingCondition: r.hull_coating_condition || '',
      cavitationFound: r.cavitation_found || '',
    }))
    .sort((a, b) => a.eventDay - b.eventDay)

  // For each maintenance event, compute before/after speed loss & estimated fuel
  const WINDOW_DAYS = 5
  const effectivenessEvents: MaintenanceEffectivenessEvent[] = []

  for (const maint of shipMaintenance) {
    const before = rows.filter((r) => r.day >= maint.eventDay - WINDOW_DAYS && r.day < maint.eventDay)
    const after = rows.filter((r) => r.day > maint.eventDay && r.day <= maint.eventDay + WINDOW_DAYS)

    if (before.length === 0 || after.length === 0) continue

    const slBefore = before.reduce((s, r) => s + r.speedLossPct, 0) / before.length
    const slAfter = after.reduce((s, r) => s + r.speedLossPct, 0) / after.length

    // Estimate fuel consumption from speed loss
    const fuelBefore = baselineFuelMt * (1 + Math.max(0, slBefore) / 100 * 1.8)
    const fuelAfter = baselineFuelMt * (1 + Math.max(0, slAfter) / 100 * 1.8)
    const fuelImprovementMt = fuelBefore - fuelAfter
    const improvementPct = fuelBefore > 0 ? (fuelImprovementMt / fuelBefore) * 100 : 0

    const eventType = CORRELATION_TYPE_MAP[maint.eventType] || 'Hull Cleaning'

    // Anomaly detection
    let isAnomaly = false
    let anomalyReason: string | null = null
    if (maint.eventType === 'DD' && improvementPct < 2) {
      isAnomaly = true
      anomalyReason = `進塢 (DD) 後 Speed Loss 改善不明顯 (${improvementPct.toFixed(1)}%)，建議確認塗裝品質。`
    } else if ((maint.eventType === 'UWC' || maint.eventType === 'UWC+PP') && improvementPct < 0) {
      isAnomaly = true
      anomalyReason = `船殼清洗後效能未改善，可能存在嚴重結構性污損或塗裝失效。`
    } else if (maint.eventType === 'PP' && improvementPct > 15) {
      isAnomaly = true
      anomalyReason = `螺旋槳拋光改善幅度異常高 (${improvementPct.toFixed(1)}%)，可能有其他因素。`
    }

    // Estimate cost based on event type
    const costEstimate: Record<string, number> = {
      DD: 500000,
      'UWC+PP': 45000,
      UWC: 35000,
      'UWI+PP': 25000,
      PP: 15000,
      UWI: 8000,
    }

    effectivenessEvents.push({
      id: `${shipId}-${maint.eventType}-${maint.eventDay}`,
      date: dayToDate(maint.eventDay),
      type: eventType,
      port: '—', // not in competition data
      fuelBefore: Number(fuelBefore.toFixed(2)),
      fuelAfter: Number(fuelAfter.toFixed(2)),
      fuelImprovementMt: Number(fuelImprovementMt.toFixed(2)),
      improvementPct: Number(improvementPct.toFixed(1)),
      speedLossBefore: Number(slBefore.toFixed(2)),
      speedLossAfter: Number(slAfter.toFixed(2)),
      isAnomaly,
      anomalyReason,
      costUsd: costEstimate[maint.eventType] || 30000,
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
  const avgImprovementPct = effectivenessEvents.length > 0
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

  // Optimal timing recommendation
  const currentSL = vessel.speedLossPct
  const rate = vessel.degradationRatePctPerDay
  const optimalThreshold = 8
  const daysUntilThreshold = rate > 0 ? Math.max(0, Math.round((optimalThreshold - currentSL) / rate)) : 90

  let recommendedAction: MaintenanceEventType = 'Hull Cleaning'
  if (currentSL >= 12) recommendedAction = 'Hull Cleaning + PP'
  else if (currentSL < 4) recommendedAction = 'Propeller Polishing'

  const excessFuelPerDay = baselineFuelMt * (Math.max(0, currentSL) / 100) * 1.8
  const excessFuelCostPerDayUsd = Math.round(excessFuelPerDay * fuelPrice)
  const avgBestImprovement = typeEffectiveness.length > 0 ? typeEffectiveness[0].avgImprovementPct : 5
  const projectedFuelSavedMtPerDay = baselineFuelMt * (avgBestImprovement / 100) * 1.8
  const projectedSavingsUsd = Math.round(projectedFuelSavedMtPerDay * fuelPrice * 90)

  const lastRow = rows[rows.length - 1]
  const windowStart = dayToDate(lastRow.day + daysUntilThreshold)
  const windowEnd = dayToDate(lastRow.day + daysUntilThreshold + 14)

  let urgency: 'LOW' | 'MEDIUM' | 'HIGH' = 'LOW'
  if (currentSL >= 10 || daysUntilThreshold <= 7) urgency = 'HIGH'
  else if (currentSL >= 6 || daysUntilThreshold <= 30) urgency = 'MEDIUM'

  let reasoning: string
  if (urgency === 'HIGH') {
    reasoning = `目前 Speed Loss ${currentSL.toFixed(1)}% 已超過經濟效益閾值，每日超額油耗成本約 $${excessFuelCostPerDayUsd.toLocaleString()}。建議立即安排 ${recommendedAction}。`
  } else if (urgency === 'MEDIUM') {
    reasoning = `目前 Speed Loss ${currentSL.toFixed(1)}%，以衰退速率 ${(rate * 30).toFixed(2)}%/月 推算，約 ${daysUntilThreshold} 天後達到介入閾值。`
  } else {
    reasoning = `目前 Speed Loss ${currentSL.toFixed(1)}% 處於正常範圍，建議依標準週期安排維護。`
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
}
