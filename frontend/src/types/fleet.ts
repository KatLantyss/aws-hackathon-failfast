// Shared front-end data shapes. Mirrors backend/app/schemas.py where applicable,
// extended with fields the UI needs (position, fouling grade, etc.) that will
// eventually be served by additional endpoints. See design_docs for the API
// response shapes this is modeled after.

export type Urgency = 'LOW' | 'MEDIUM' | 'HIGH'
export type FoulingGrade = 'Clean' | 'Light' | 'Moderate' | 'Heavy'
export type VesselStatus = 'underway' | 'moored' | 'anchored'
export type LoadCondition = 'ballast' | 'laden'
export type Confidence = 'high' | 'medium' | 'low'
export type MaintenanceStatus = 'normal' | 'needs_request' | 'requested' | 'in_progress'

export interface VesselPosition {
  lat: number
  lon: number
  headingDeg: number
  speedKt: number
  courseTrueDeg: number
}

export interface VesselSummary {
  imo: string
  name: string
  type: string
  shipClass: string           // 'W1' | 'W2'
  teuCapacity: number
  builtYear: number
  flag: string
  mainEngineModel: string
  tradeRoute: string
  status: VesselStatus
  currentPort: string | null
  destinationPort: string | null
  position: VesselPosition
  // slip / speed loss
  speedLossPct: number
  avgSlipPct: number | null
  slipTrend: number | null         // + = degrading, - = improving
  validSlipRecords: number | null
  foulingGrade: FoulingGrade
  // performance averages
  avgSpeedKn: number | null
  avgStwKn: number | null
  avgRpm: number | null
  avgConsumptionMt: number | null
  avgSfoc: number | null
  avgLoadPct: number | null
  // environment averages
  avgWindScale: number | null
  avgSeaHeightM: number | null
  avgSeaWaterTempC: number | null
  // loading averages
  avgForeDraftM: number | null
  avgAftDraftM: number | null
  avgCargoOnBoardMt: number | null
  // voyage coverage
  totalRecords: number
  totalVoyages: number
  dataDayMin: number | null
  dataDayMax: number | null
  dataSpanDays: number | null
  // maintenance
  lastDrydockDay: number | null
  nextDrydockDueDay: number | null
  daysSinceHullClean: number
  daysSinceMaintenance: number | null
  daysSincePropPolish: number | null
  totalMaintEvents: number | null
  lastEventType: string | null
  lastHullCleanType: string | null
  maintenanceUrgency: Urgency
  maintenanceStatus: MaintenanceStatus
  // cost
  degradationRatePctPerDay: number
  excessFuelCostUsdMtd: number
  nextRecommendedWindow: { startDay: number; endDay: number }
}

export interface PortCallEntry {
  port: string
  arrival: string
  departure: string
}

export interface NoonReportEntry {
  day: number
  lat: number
  lon: number
  observedSpeedKt: number
  correctedSpeedKt: number
  speedLossPct: number
  fuelConsumptionMt: number
  beaufort: number
  seaState: number
  draftFwd: number
  draftAft: number
  loadCondition: LoadCondition
}

export interface SpeedLossEvent {
  day: number
  type: 'hull_cleaning' | 'propeller_polishing' | 'drydock'
  label: string
}

export interface SpeedLossSeries {
  vessel: { imo: string; name: string; type: string }
  events: SpeedLossEvent[]
  reports: NoonReportEntry[]
}

export interface FuelAttributionFactor {
  factor: 'weather' | 'hull_fouling' | 'propeller_fouling' | 'engine_degradation'
  impactMt: number
  label: string
}

export interface FuelAttributionTimePoint {
  date: string
  weather: number
  hull_fouling: number
  propeller_fouling: number
  engine_degradation: number
}

export interface FuelAttributionResponse {
  baselineFuelMt: number
  actualFuelMt: number
  attribution: FuelAttributionFactor[]
  confidence: Confidence
  timeSeries: FuelAttributionTimePoint[]
}

export interface CostBenefitPoint {
  deferralDays: number
  cumulativeExcessFuelCostUsd: number
}

export interface MaintenanceRecommendation {
  action: string
  windowStartDay: number
  windowEndDay: number
  estimatedSavingUsd: number
  confidence: Confidence
  reasoning: string
  dataLimitations: string[]
  curve: CostBenefitPoint[]
}

export interface FleetKpis {
  totalVessels: number
  underway: number
  inPort: number
  pendingMaintenance: number
  monthlyExcessFuelCostUsd: number
}

// ─── Maintenance-Performance Correlation Analysis ─────────────────────────────

export type MaintenanceEventType = 'Hull Cleaning' | 'Propeller Polishing' | 'Hull Cleaning + PP' | 'Dry Dock'

export interface MaintenanceEffectivenessEvent {
  id: string
  day: number
  type: MaintenanceEventType
  port: string
  /** Average daily fuel consumption (MT/day) in the 5-day window BEFORE maintenance */
  fuelBefore: number
  /** Average daily fuel consumption (MT/day) in the 5-day window AFTER maintenance */
  fuelAfter: number
  /** Absolute improvement in MT/day */
  fuelImprovementMt: number
  /** Improvement percentage */
  improvementPct: number
  /** Speed loss % before maintenance */
  speedLossBefore: number
  /** Speed loss % after maintenance */
  speedLossAfter: number
  /** Whether the result is anomalous (e.g. no improvement after DD) */
  isAnomaly: boolean
  /** Anomaly explanation if applicable */
  anomalyReason: string | null
}

export interface MaintenanceTypeEffectiveness {
  type: MaintenanceEventType
  /** Number of events of this type */
  eventCount: number
  /** Average fuel improvement (MT/day) */
  avgFuelImprovementMt: number
  /** Average improvement percentage */
  avgImprovementPct: number
  /** Star rating 1-5 */
  rating: number
}

export interface PerformanceTimelinePoint {
  day: number
  fuelConsumptionMt: number
  speedLossPct: number
}

export interface MaintenanceCorrelationResponse {
  vessel: { imo: string; name: string }
  /** Full timeline of fuel & speed loss with maintenance markers */
  timeline: PerformanceTimelinePoint[]
  /** Individual maintenance events with before/after analysis */
  events: MaintenanceEffectivenessEvent[]
  /** Aggregated effectiveness per maintenance type */
  typeEffectiveness: MaintenanceTypeEffectiveness[]
  /** AI-driven optimal maintenance timing recommendation */
  optimalTiming: OptimalMaintenanceTiming
  /** Summary stats */
  summary: {
    totalEvents: number
    avgImprovementPct: number
    bestEventId: string
    worstEventId: string
    anomalyCount: number
    totalFuelSavedMt: number
  }
}

export interface OptimalMaintenanceTiming {
  /** Recommended action type */
  recommendedAction: MaintenanceEventType
  /** Current speed loss % */
  currentSpeedLossPct: number
  /** Current degradation rate (%/day) */
  degradationRatePerDay: number
  /** Optimal intervention threshold (speed loss %) */
  optimalThresholdPct: number
  /** Estimated days until threshold */
  daysUntilThreshold: number
  /** Recommended window, as day-index (raw dataset has no calendar date) */
  windowStartDay: number
  windowEndDay: number
  /** If deferred: projected extra fuel cost per day (USD) */
  excessFuelCostPerDayUsd: number
  /** Total projected savings from timely intervention (USD) */
  projectedSavingsUsd: number
  /** Reasoning text */
  reasoning: string
  /** Severity: how urgent is this? */
  urgency: 'LOW' | 'MEDIUM' | 'HIGH'
}
