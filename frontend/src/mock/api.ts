// Frontend "API" layer — despite the module name/path (kept for a minimal
// diff against the pre-existing convention documented in CLAUDE.md), every
// function below is now backed by the real deployed backend
// (src/services/backend.ts), not synthetic data. Exported function
// signatures/return shapes match src/types/fleet.ts exactly as before, so
// every view/composable that imports from '@/mock/api' keeps working
// unchanged — only the implementation swapped from generator to adapter.
//
// The backend has no decorative vessel metadata (name, flag, TEU, AIS
// position...) — that stays illustrative, generated in ./reference.ts.
// Every *analytical* number (speed loss, fuel consumption, maintenance
// history, degradation trend) is derived from real API responses.

import * as backend from '@/services/backend'
import type { BackendMaintenanceEvent, BackendNoonReport, BackendSpeedLoss } from '@/services/backend'
import { ALL_VESSEL_IDS, VESSEL_REFS, VESSEL_LIVE_STATE } from './reference.ts'
import { addDays, createRng } from './seed.ts'
import type {
  VesselSummary,
  FoulingGrade,
  InspectionEntry,
  SpeedLossSeries,
  SpeedLossEvent,
  NoonReportEntry,
  LoadCondition,
  FuelAttributionResponse,
  FuelAttributionFactor,
  AttributionEventEntry,
  MaintenanceRecommendation,
  CostBenefitPoint,
  FleetKpis,
  Urgency,
  Confidence,
  FuelPredictionInput,
  FuelPredictionResult,
} from '@/types/fleet'

// Backend noon_day is a relative day count (0 = first day of that vessel's
// record), not a calendar date. We project it onto a synthetic calendar so
// the rest of the UI (date filters, regression-by-cycle, CSV export) keeps
// working unchanged; it is NOT a real historical date.
const EPOCH = '2019-01-01'
function dayToDate(day: number): string {
  return addDays(EPOCH, Math.round(day))
}

function median(values: number[]): number {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

function meanStd(values: number[]): { mean: number; std: number } {
  if (!values.length) return { mean: 0, std: 0 }
  const mean = values.reduce((s, v) => s + v, 0) / values.length
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length
  return { mean, std: Math.sqrt(variance) }
}

function linearRegression(points: { x: number; y: number }[]) {
  const n = points.length
  if (n < 2) return { slope: 0, intercept: points[0]?.y ?? 0 }
  const sumX = points.reduce((s, p) => s + p.x, 0)
  const sumY = points.reduce((s, p) => s + p.y, 0)
  const sumXY = points.reduce((s, p) => s + p.x * p.y, 0)
  const sumXX = points.reduce((s, p) => s + p.x * p.x, 0)
  const denom = n * sumXX - sumX * sumX
  const slope = denom === 0 ? 0 : (n * sumXY - sumX * sumY) / denom
  const intercept = (sumY - slope * sumX) / n
  return { slope, intercept }
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

/** Illustrative position along a per-vessel seeded random walk — the real backend has no AIS/location data at all (not even for the live fleet map), so per-row position here is decorative continuity, not a real track. */
function syntheticTrackPoint(vesselId: string, noonDay: number): { lat: number; lon: number } {
  const rng = createRng(`${vesselId}-track`)
  const base = VESSEL_LIVE_STATE[vesselId]
  const wobble = (seedOffset: number) => Math.sin(noonDay / 45 + seedOffset) * 12
  return {
    lat: Number(Math.max(-60, Math.min(65, base.lat + wobble(rng() * 10))).toFixed(2)),
    lon: Number((((base.lon + wobble(rng() * 10 + 5) + 180) % 360 + 360) % 360 - 180).toFixed(2)),
  }
}

function dedupeByNoonDay(rows: BackendNoonReport[]): BackendNoonReport[] {
  const seen = new Set<number>()
  const out: BackendNoonReport[] = []
  for (const r of rows) {
    if (seen.has(r.noon_day)) continue
    seen.add(r.noon_day)
    out.push(r)
  }
  return out
}

function detectAnomaly(row: BackendNoonReport, consumpMean: number, consumpStd: number): { isAnomaly: boolean; reason: string | null } {
  if (row.me_slip != null && (row.me_slip < 0 || row.me_slip > 30)) {
    return { isAnomaly: true, reason: `ME_SLIP ${row.me_slip.toFixed(1)}% 超出正常範圍 (0–30%)，疑似感測器或資料異常` }
  }
  if (consumpStd > 0 && row.total_consump != null) {
    const z = (row.total_consump - consumpMean) / consumpStd
    if (Math.abs(z) > 2.5) {
      return { isAnomaly: true, reason: `當日油耗 ${row.total_consump.toFixed(1)} MT 偏離本船平均 ${Math.abs(z).toFixed(1)} 個標準差（Z-score 偵測）` }
    }
  }
  return { isAnomaly: false, reason: null }
}

function urgencyFor(recommendation: backend.BackendMaintenanceRecommendation): Urgency {
  if (recommendation.recommendation === 'URGENT') return 'HIGH'
  if (recommendation.avg_me_slip_pct >= 5) return 'MEDIUM'
  return 'LOW'
}

function buildSpeedLossEvents(events: BackendMaintenanceEvent[]): SpeedLossEvent[] {
  return [...events]
    .sort((a, b) => a.event_day - b.event_day)
    .map((e) => {
      const date = dayToDate(e.event_day)
      switch (e.event_type) {
        case 'DD':
          return { date, type: 'drydock' as const, label: '坐塢 (DD)' }
        case 'UWC':
          return { date, type: 'hull_cleaning' as const, label: '船體清洗 (UWC)' }
        case 'UWC+PP':
          return { date, type: 'hull_cleaning' as const, label: '船體清洗+螺旋槳拋光 (UWC+PP)' }
        case 'PP':
          return { date, type: 'propeller_polishing' as const, label: '螺旋槳拋光 (PP)' }
        case 'UWI+PP':
          return { date, type: 'propeller_polishing' as const, label: '檢查+螺旋槳拋光 (UWI+PP)' }
        case 'UWI':
          return { date, type: 'inspection' as const, label: '水下檢查 (UWI，僅檢查無介入)' }
        default:
          return { date, type: 'inspection' as const, label: e.event_type }
      }
    })
}

// simulate a touch of network latency so Loading states are still exercised
// even when the real backend responds very fast
function withMinLatency<T>(promise: Promise<T>, minMs = 150): Promise<T> {
  return Promise.all([promise, new Promise((r) => setTimeout(r, minMs))]).then(([v]) => v)
}

// --- shared per-vessel fetch + cache -----------------------------------

interface VesselCore {
  detail: backend.BackendVesselDetail
  speedLoss: BackendSpeedLoss
  maintenanceEvents: BackendMaintenanceEvent[]
  recommendation: backend.BackendMaintenanceRecommendation
}

const coreCache = new Map<string, Promise<VesselCore | null>>()
const noonReportsCache = new Map<string, Promise<BackendNoonReport[]>>()
const attributionCache = new Map<string, Promise<backend.BackendSpeedLossAttribution | null>>()

// The deployed backend's GET /vessels/{id} and .../maintenance-recommendation
// 500 for the prediction-set vessels (S21/S22/S23 — confirmed against the
// live API: "can't convert type 'NoneType' to numerator/denominator",
// consistent with those rows having no historical ME_CONSUMPTION to
// average, since predicting that value is the whole point of that vessel
// set). POST /predict/fuel-consumption itself is unaffected. Rather than
// let those vessels disappear from the app, fall back to computing the
// same aggregates locally from data that IS available (raw noon-reports,
// the speed-loss timeline, maintenance-events) — same methodology the
// backend documents, just run client-side when its own endpoint errors.

function buildDetailFallback(vesselId: string, rows: BackendNoonReport[]): backend.BackendVesselDetail {
  const mean = (vals: (number | null)[]) => {
    const nums = vals.filter((v): v is number => v != null)
    return nums.length ? nums.reduce((s, v) => s + v, 0) / nums.length : 0
  }
  const voyages = rows.map((r) => r.voyage).filter((v): v is number => v != null)
  return {
    vessel_id: vesselId,
    total_records: rows.length,
    avg_speed_kn: mean(rows.map((r) => r.avg_speed_kn)),
    avg_consumption: mean(rows.map((r) => r.total_consump)),
    avg_stw_kn: mean(rows.map((r) => r.speed_through_water)),
    voyage_range: { min: voyages.length ? Math.min(...voyages) : 0, max: voyages.length ? Math.max(...voyages) : 0 },
  }
}

function buildRecommendationFallback(speedLoss: BackendSpeedLoss, maintenanceEvents: BackendMaintenanceEvent[]): backend.BackendMaintenanceRecommendation {
  const latestDay = latestSlipDay(speedLoss)
  const last = [...maintenanceEvents].sort((a, b) => a.event_day - b.event_day).pop() ?? null
  const daysSinceMaintenance = Math.max(0, Math.round(latestDay - (last?.event_day ?? 0)))
  const recentWindow = speedLoss.slip_timeline.filter((p) => p.noon_day >= latestDay - 90)
  const avgMeSlipPct = recentWindow.length
    ? recentWindow.reduce((s, p) => s + p.slip_pct, 0) / recentWindow.length
    : speedLoss.slip_summary.avg_slip_pct
  const urgent = avgMeSlipPct > 10 || daysSinceMaintenance > 365
  return {
    vessel_id: speedLoss.vessel_id,
    days_since_maintenance: daysSinceMaintenance,
    avg_me_slip_pct: Number(avgMeSlipPct.toFixed(2)),
    recommendation: urgent ? 'URGENT' : 'ROUTINE',
    recommended_type: daysSinceMaintenance > 730 ? 'DD' : 'UWC',
    reason: `[前端本地估算 — 後端 maintenance-recommendation 端點對此船回應異常] ${urgent ? '近期 ME Slip 偏高或距上次維護過久' : '依排定週期建議維護'}（距上次事件 ${daysSinceMaintenance} 天）`,
    last_maintenance: last ? { event_type: last.event_type, event_day: last.event_day } : null,
  }
}

function loadVesselCore(vesselId: string): Promise<VesselCore | null> {
  let cached = coreCache.get(vesselId)
  if (!cached) {
    cached = Promise.all([
      backend.getVesselDetail(vesselId).then((d) => ({ ok: true as const, d })).catch(() => ({ ok: false as const })),
      backend.getSpeedLoss(vesselId).catch(() => null),
      backend.getMaintenanceEvents(vesselId).catch(() => ({ vessel_id: vesselId, total: 0, events: [] })),
      backend.getMaintenanceRecommendation(vesselId).then((r) => ({ ok: true as const, r })).catch(() => ({ ok: false as const })),
    ]).then(async ([detailResult, speedLoss, maintenance, recommendationResult]) => {
      if (!speedLoss) return null
      const maintenanceEvents = maintenance.events
      const detail = detailResult.ok ? detailResult.d : buildDetailFallback(vesselId, await loadNoonReports(vesselId))
      const recommendation = recommendationResult.ok ? recommendationResult.r : buildRecommendationFallback(speedLoss, maintenanceEvents)
      return { detail, speedLoss, maintenanceEvents, recommendation }
    })
    coreCache.set(vesselId, cached)
  }
  return cached
}

function loadNoonReports(vesselId: string): Promise<BackendNoonReport[]> {
  let cached = noonReportsCache.get(vesselId)
  if (!cached) {
    cached = backend
      .getNoonReports(vesselId, { limit: 5000 })
      .then((res) => dedupeByNoonDay(res.records))
      .catch(() => [])
    noonReportsCache.set(vesselId, cached)
  }
  return cached
}

function loadAttribution(vesselId: string): Promise<backend.BackendSpeedLossAttribution | null> {
  let cached = attributionCache.get(vesselId)
  if (!cached) {
    cached = backend.getSpeedLossAttribution(vesselId).catch(() => null)
    attributionCache.set(vesselId, cached)
  }
  return cached
}

// --- vessel summary -------------------------------------------------------

function degradationRatePctPerDay(speedLoss: BackendSpeedLoss, sinceDay: number | null): number {
  const points = speedLoss.slip_timeline
    .filter((p) => sinceDay == null || p.noon_day >= sinceDay)
    .map((p) => ({ x: p.noon_day, y: p.slip_pct }))
  return Number(linearRegression(points).slope.toFixed(4))
}

function latestSlipDay(speedLoss: BackendSpeedLoss): number {
  return speedLoss.slip_timeline.reduce((max, p) => Math.max(max, p.noon_day), 0)
}

async function buildVesselSummary(vesselId: string): Promise<VesselSummary | null> {
  const ref = VESSEL_REFS.find((v) => v.imo === vesselId)
  const live = VESSEL_LIVE_STATE[vesselId]
  const core = await loadVesselCore(vesselId)
  if (!ref || !live || !core) return null
  const { detail, speedLoss, maintenanceEvents, recommendation } = core

  const currentSpeedLossPct = Math.max(0, recommendation.avg_me_slip_pct)
  const ddEvents = maintenanceEvents.filter((e) => e.event_type === 'DD').sort((a, b) => a.event_day - b.event_day)
  const lastDD = ddEvents[ddEvents.length - 1] ?? null
  const lastDrydockDate = dayToDate(lastDD?.event_day ?? 0)
  const nextDrydockDue = addDays(lastDrydockDate, 5 * 365) // illustrative 5-year cycle; backend has no scheduling data

  const lastEventDay = recommendation.last_maintenance?.event_day ?? null
  const rate = degradationRatePctPerDay(speedLoss, lastEventDay)

  const fuelPriceUsdPerMt = 620
  const baselineFuel = detail.avg_consumption / (1 + currentSpeedLossPct / 100 * 1.8)
  const excessFuelPerDay = Math.max(0, detail.avg_consumption - baselineFuel)

  const latestDay = latestSlipDay(speedLoss)
  const daysToThreshold = rate > 0 ? Math.max(5, Math.round((8 - currentSpeedLossPct) / rate)) : 120
  const windowStart = dayToDate(latestDay + Math.max(3, daysToThreshold - 7))
  const windowEnd = dayToDate(latestDay + Math.max(10, daysToThreshold + 7))

  return {
    imo: vesselId,
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
    position: { lat: live.lat, lon: live.lon, headingDeg: live.headingDeg, speedKt: live.speedKt, courseTrueDeg: live.headingDeg },
    speedLossPct: Number(currentSpeedLossPct.toFixed(2)),
    foulingGrade: speedLossToGrade(currentSpeedLossPct),
    lastDrydockDate,
    nextDrydockDue,
    daysSinceHullClean: recommendation.days_since_maintenance,
    maintenanceUrgency: urgencyFor(recommendation),
    degradationRatePctPerDay: rate,
    excessFuelCostUsdMtd: Math.round(excessFuelPerDay * 30 * fuelPriceUsdPerMt),
    nextRecommendedWindow: { start: windowStart, end: windowEnd },
  }
}

export async function fetchFleetKpis(): Promise<FleetKpis> {
  const summaries = await fetchFleetVessels()
  return {
    totalVessels: summaries.length,
    underway: summaries.filter((s) => s.status === 'underway').length,
    inPort: summaries.filter((s) => s.status !== 'underway').length,
    pendingMaintenance: summaries.filter((s) => s.maintenanceUrgency !== 'LOW').length,
    monthlyExcessFuelCostUsd: summaries.reduce((sum, s) => sum + s.excessFuelCostUsdMtd, 0),
  }
}

export async function fetchFleetVessels(): Promise<VesselSummary[]> {
  const results = await withMinLatency(Promise.all(ALL_VESSEL_IDS.map((id) => buildVesselSummary(id))))
  return results.filter((s): s is VesselSummary => s != null)
}

export async function fetchVessel(imo: string): Promise<VesselSummary | null> {
  if (!ALL_VESSEL_IDS.includes(imo)) return null
  return withMinLatency(buildVesselSummary(imo))
}

// --- noon reports (raw data page — every fetched record, unfiltered) -----

function toNoonReportEntry(
  vesselId: string,
  row: BackendNoonReport,
  designDraftM: number,
  cargoMedian: number,
  consumpMean: number,
  consumpStd: number,
): NoonReportEntry {
  const anomaly = detectAnomaly(row, consumpMean, consumpStd)
  const cargo = row.cargo_on_board ?? cargoMedian
  const loadCondition: LoadCondition = cargo >= cargoMedian ? 'laden' : 'ballast'
  const track = syntheticTrackPoint(vesselId, row.noon_day)
  return {
    date: dayToDate(row.noon_day),
    lat: track.lat,
    lon: track.lon,
    observedSpeedKt: row.speed_through_water ?? row.avg_speed_kn ?? 0,
    correctedSpeedKt: row.avg_speed_kn ?? 0,
    speedLossPct: row.me_slip ?? 0,
    fuelConsumptionMt: row.total_consump ?? 0,
    beaufort: row.wind_scale ?? 0,
    seaState: Math.min(9, Math.round(row.sea_height ?? 0)),
    draftFwd: row.fore_draft ?? designDraftM,
    draftAft: row.aft_draft ?? designDraftM,
    loadCondition,
    isAnomaly: anomaly.isAnomaly,
    anomalyReason: anomaly.reason,
  }
}

export async function fetchNoonReports(imo: string): Promise<{ vessel: VesselSummary; reports: NoonReportEntry[] } | null> {
  if (!ALL_VESSEL_IDS.includes(imo)) return null
  const ref = VESSEL_REFS.find((v) => v.imo === imo)!
  const [vessel, rows] = await withMinLatency(Promise.all([fetchVessel(imo), loadNoonReports(imo)]))
  if (!vessel || !rows.length) return null

  const cargoMedian = median(rows.map((r) => r.cargo_on_board).filter((v): v is number => v != null))
  const { mean, std } = meanStd(rows.map((r) => r.total_consump).filter((v): v is number => v != null))

  const reports = rows
    .map((r) => toNoonReportEntry(imo, r, ref.designDraftM, cargoMedian, mean, std))
    .sort((a, b) => (a.date < b.date ? -1 : 1))

  return { vessel, reports }
}

// --- speed loss (core page) — reports come from the backend's own
// validated slip_timeline (same rows counted in slip_summary.valid_records),
// enriched with noon-report fields for display only ---------------------

export async function fetchSpeedLoss(imo: string): Promise<SpeedLossSeries | null> {
  if (!ALL_VESSEL_IDS.includes(imo)) return null
  const ref = VESSEL_REFS.find((v) => v.imo === imo)!
  const [core, rows] = await withMinLatency(Promise.all([loadVesselCore(imo), loadNoonReports(imo)]))
  if (!core || !rows.length) return null
  const { speedLoss, maintenanceEvents, detail } = core
  if (!speedLoss.slip_timeline.length) return null

  const noonByDay = new Map<number, BackendNoonReport>()
  for (const r of rows) if (!noonByDay.has(r.noon_day)) noonByDay.set(r.noon_day, r)

  const cargoMedian = median(rows.map((r) => r.cargo_on_board).filter((v): v is number => v != null))
  const { mean, std } = meanStd(rows.map((r) => r.total_consump).filter((v): v is number => v != null))

  const reports: NoonReportEntry[] = [...speedLoss.slip_timeline]
    .sort((a, b) => a.noon_day - b.noon_day)
    .map((p) => {
      const match = noonByDay.get(p.noon_day)
      const cargo = match?.cargo_on_board ?? cargoMedian
      const loadCondition: LoadCondition = cargo >= cargoMedian ? 'laden' : 'ballast'
      const track = syntheticTrackPoint(imo, p.noon_day)
      const anomaly = match ? detectAnomaly(match, mean, std) : { isAnomaly: false, reason: null }
      return {
        date: dayToDate(p.noon_day),
        lat: track.lat,
        lon: track.lon,
        observedSpeedKt: match?.speed_through_water ?? match?.avg_speed_kn ?? 0,
        correctedSpeedKt: match?.avg_speed_kn ?? 0,
        speedLossPct: p.slip_pct, // authoritative value from the backend's own Speed Loss calculation
        fuelConsumptionMt: match?.total_consump ?? 0,
        beaufort: p.wind_scale ?? match?.wind_scale ?? 0,
        seaState: Math.min(9, Math.round(match?.sea_height ?? 0)),
        draftFwd: match?.fore_draft ?? ref.designDraftM,
        draftAft: match?.aft_draft ?? ref.designDraftM,
        loadCondition,
        isAnomaly: anomaly.isAnomaly,
        anomalyReason: anomaly.reason,
      }
    })

  return {
    vessel: { imo, name: ref.name, type: ref.vesselType },
    cleanBaseline: { speedKnots: Number(detail.avg_stw_kn.toFixed(2)), source: speedLoss.method },
    events: buildSpeedLossEvents(maintenanceEvents),
    reports,
  }
}

// --- inspections (derived from UWI / UWI+PP maintenance events, the only
// backend records that carry underwater-survey findings) ----------------

function inspectionFoulingScore(e: BackendMaintenanceEvent): number {
  if (!e.hull_fouling_type) return 0
  const weight: Record<string, number> = { slime: 15, algae: 20, barnacle: 35, calcium: 30 }
  const types = e.hull_fouling_type.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean)
  return Math.min(100, types.reduce((sum, t) => sum + (weight[t] ?? 20), 0))
}

export async function fetchInspections(imo: string): Promise<InspectionEntry[]> {
  if (!ALL_VESSEL_IDS.includes(imo)) return []
  const core = await withMinLatency(loadVesselCore(imo))
  if (!core) return []
  const uwiEvents = core.maintenanceEvents.filter((e) => e.event_type.includes('UWI'))

  return uwiEvents
    .map((e): InspectionEntry => {
      const score = inspectionFoulingScore(e)
      const notes = [
        e.hull_fouling_type ? `污損類型: ${e.hull_fouling_type}` : null,
        e.hull_coating_condition ? `塗層狀況: ${e.hull_coating_condition}` : null,
        e.cavitation_found ? `發現空蝕(cavitation): ${e.cavitation_found}` : null,
      ]
        .filter(Boolean)
        .join('；')
      return {
        id: `${imo}-${e.event_type}-${e.event_day}`,
        date: dayToDate(e.event_day),
        port: '未記錄（後端無港口資料）',
        surveyor: '未記錄（後端無驗船公司資料）',
        method: e.event_type === 'UWI+PP' ? 'ROV/潛水檢查 + 螺旋槳拋光' : 'ROV/潛水檢查',
        foulingGrade: biofoulingScoreToGrade(score),
        biofoulingScore: score,
        paintBreakdownPct: 0,
        propellerCondition: e.propeller_condition ?? '未記錄',
        cleaningRecommended: e.event_type === 'UWI+PP' ? 'YES（本次已執行螺旋槳拋光）' : score >= 50 ? 'YES - PRIORITY' : 'NO',
        notes: notes || '本次檢查無詳細污損記錄',
        hullSections: [],
        photoCount: 0,
        reportUrl: null,
      }
    })
    .sort((a, b) => (a.date < b.date ? 1 : -1))
}

// --- fuel / speed-loss attribution ---------------------------------------

const ASSUMED_FUEL_PRICE_USD_PER_MT = 620

export async function fetchFuelAttribution(imo: string): Promise<FuelAttributionResponse | null> {
  if (!ALL_VESSEL_IDS.includes(imo)) return null
  const [core, attribution, rows] = await withMinLatency(Promise.all([loadVesselCore(imo), loadAttribution(imo), loadNoonReports(imo)]))
  if (!core || !attribution) return null
  const { detail, speedLoss } = core

  const currentSlipPct = Math.max(0, speedLoss.slip_summary.avg_slip_pct)
  const actualFuelMt = Number(detail.avg_consumption.toFixed(2))
  const baselineFuelMt = Number((actualFuelMt / (1 + currentSlipPct / 100 * 1.8)).toFixed(2))
  const excessTotalMt = Math.max(0, actualFuelMt - baselineFuelMt)

  const summary = attribution.summary
  const hullRaw = Math.abs(summary.hull ?? 0) + Math.abs(summary['hull+propeller'] ?? 0) * 0.5
  const propRaw = Math.abs(summary.propeller ?? 0) + Math.abs(summary['hull+propeller'] ?? 0) * 0.5
  const otherRaw = Math.abs(summary.other ?? 0)
  const totalRaw = hullRaw + propRaw + otherRaw
  const scale = totalRaw > 0 ? excessTotalMt / totalRaw : 0
  const hullShare = totalRaw > 0 ? hullRaw / totalRaw : 0
  const propShare = totalRaw > 0 ? propRaw / totalRaw : 0
  const otherShare = totalRaw > 0 ? otherRaw / totalRaw : 0

  const attributionFactors: FuelAttributionFactor[] = [
    { factor: 'weather', impactMt: 0, label: '天氣（風浪，本歸因模型未單獨拆分）' },
    { factor: 'hull_fouling', impactMt: Number((hullRaw * scale).toFixed(2)), label: '船體污損' },
    { factor: 'propeller_fouling', impactMt: Number((propRaw * scale).toFixed(2)), label: '螺旋槳污損' },
    { factor: 'engine_degradation', impactMt: Number((otherRaw * scale).toFixed(2)), label: '其他因子' },
  ]

  const recent = rows.slice(-60)
  const timeSeries = recent.map((r) => {
    const slip = Math.max(0, r.me_slip ?? 0)
    const fuel = r.total_consump ?? actualFuelMt
    const baseline = fuel / (1 + slip / 100 * 1.8)
    const excess = Math.max(0, fuel - baseline)
    return {
      date: dayToDate(r.noon_day),
      weather: 0,
      hull_fouling: Number((excess * hullShare).toFixed(2)),
      propeller_fouling: Number((excess * propShare).toFixed(2)),
      engine_degradation: Number((excess * otherShare).toFixed(2)),
    }
  })

  const eventCount = attribution.event_attributions.length
  const confidence: Confidence = eventCount >= 4 ? 'high' : eventCount >= 2 ? 'medium' : 'low'

  const events: AttributionEventEntry[] = attribution.event_attributions.map((e) => ({
    eventType: e.event_type,
    date: dayToDate(e.event_day),
    category: e.category,
    physicalIntervention: e.physical_intervention,
    slipBeforePct: e.slip_before_pct,
    slipAfterPct: e.slip_after_pct,
    slipDeltaPct: e.slip_delta_pct,
    notes: e.notes,
  }))

  return { baselineFuelMt, actualFuelMt, attribution: attributionFactors, confidence, timeSeries, method: attribution.method, events }
}

// --- maintenance recommendation (curve is client-derived from the real
// degradation trend + real predicted fuel cost; backend gives one point-in-
// time recommendation, not a 90-day curve) --------------------------------

export async function fetchMaintenanceRecommendation(imo: string): Promise<MaintenanceRecommendation | null> {
  if (!ALL_VESSEL_IDS.includes(imo)) return null
  const core = await withMinLatency(loadVesselCore(imo))
  if (!core) return null
  const { detail, speedLoss, recommendation, maintenanceEvents } = core

  const currentLoss = Math.max(0, recommendation.avg_me_slip_pct)
  const lastEventDay = recommendation.last_maintenance?.event_day ?? null
  const rate = degradationRatePctPerDay(speedLoss, lastEventDay)
  const latestDay = latestSlipDay(speedLoss)

  const dailyFuelMt = detail.avg_consumption
  // Assumed order-of-magnitude intervention cost — the backend has no cost
  // data at all, so this is a labeled planning assumption (see
  // dataLimitations below), not a vessel-specific real figure.
  const assumedMaintenanceCostUsd = recommendation.recommended_type === 'DD' ? 250_000 : 35_000

  let cumulative = 0
  const curve: CostBenefitPoint[] = []
  for (let d = 0; d <= 90; d++) {
    const projectedLoss = Math.max(0, currentLoss + rate * d)
    const projectedFuel = dailyFuelMt * (1 + Math.max(0, projectedLoss - currentLoss) / 100 * 1.8)
    const excessPerDay = Math.max(0, projectedFuel - dailyFuelMt)
    cumulative += excessPerDay * ASSUMED_FUEL_PRICE_USD_PER_MT
    curve.push({ deferralDays: d, cumulativeExcessFuelCostUsd: Math.round(cumulative), opportunityCostUsd: assumedMaintenanceCostUsd })
  }

  const daysToThreshold = rate > 0 ? Math.max(5, Math.round((8 - currentLoss) / rate)) : 120
  const windowStart = dayToDate(latestDay + Math.max(3, daysToThreshold - 7))
  const windowEnd = dayToDate(latestDay + Math.max(10, daysToThreshold + 7))

  const eventCount = maintenanceEvents.length
  const confidence: Confidence = eventCount >= 4 ? 'high' : eventCount >= 2 ? 'medium' : 'low'

  const dataLimitations: string[] = [
    `假設維護成本為 ${recommendation.recommended_type === 'DD' ? '坐塢' : '水下清洗'}作業的業界量級估計（$${assumedMaintenanceCostUsd.toLocaleString()}），非本船實際報價。`,
  ]
  if (eventCount < 4) dataLimitations.push(`本船僅有 ${eventCount} 次維護紀錄，趨勢估計信心中等。`)

  return {
    action: recommendation.recommended_type === 'DD' ? 'drydock' : 'hull_cleaning',
    windowStart,
    windowEnd,
    estimatedSavingUsd: curve[curve.length - 1]?.cumulativeExcessFuelCostUsd ?? 0,
    confidence,
    reasoning: `${recommendation.reason}目前近 90 天平均 ME Slip 為 ${currentLoss.toFixed(1)}%（判定：${recommendation.recommendation}），建議維修類型：${recommendation.recommended_type === 'DD' ? '坐塢 (Dry Dock)' : '水下清洗 (UWC)'}。污損增長速率約 ${(rate * 30).toFixed(2)}%/月。`,
    dataLimitations,
    curve,
  }
}

// --- fuel consumption prediction (new — no prior mock equivalent) -------

export async function predictFuelConsumption(input: FuelPredictionInput): Promise<FuelPredictionResult> {
  const raw = await backend.predictFuelConsumption({
    vessel_id: input.vesselId,
    speed_kn: input.speedKn,
    draft_fwd: input.draftFwd,
    draft_aft: input.draftAft,
    cargo_on_board: input.cargoOnBoard,
    wind_scale: input.windScale,
    sea_height: input.seaHeight,
  })
  return {
    vesselId: raw.vessel_id,
    input: {
      vesselId: raw.vessel_id,
      speedKn: raw.input.speed_kn,
      draftFwd: raw.input.draft_fwd,
      draftAft: raw.input.draft_aft,
      cargoOnBoard: raw.input.cargo_on_board,
      windScale: raw.input.wind_scale,
      seaHeight: raw.input.sea_height,
    },
    predictedConsumptionMt: raw.predicted_consumption_mt,
    model: raw.model,
    counterfactual: {
      slowBy1KnSpeedKn: raw.counterfactual.slow_by_1kn_speed,
      predictedConsumptionMt: raw.counterfactual.predicted_consumption_mt,
      fuelSavingMt: raw.counterfactual.fuel_saving_mt,
      savingPct: raw.counterfactual.saving_pct,
    },
  }
}

/** Every noon-report row for a vessel, exposed for pages/composables that need the raw joined dataset directly (e.g. cross-fleet overlay charts) instead of the curated per-page shapes above. */
export async function fetchNoonReportSeries(imo: string): Promise<NoonReportEntry[]> {
  const result = await fetchNoonReports(imo)
  return result?.reports ?? []
}
