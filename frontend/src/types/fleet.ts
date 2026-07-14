// Shared front-end data shapes. Mirrors backend/app/schemas.py where applicable,
// extended with fields the UI needs (position, fouling grade, etc.) that will
// eventually be served by additional endpoints. See design_docs for the API
// response shapes this is modeled after.

export type Urgency = 'LOW' | 'MEDIUM' | 'HIGH'
export type FoulingGrade = 'Clean' | 'Light' | 'Moderate' | 'Heavy'
export type VesselStatus = 'underway' | 'moored' | 'anchored'
export type LoadCondition = 'ballast' | 'laden'
export type Confidence = 'high' | 'medium' | 'low'

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
  teuCapacity: number
  builtYear: number
  flag: string
  mainEngineModel: string
  designSpeedKt: number
  tradeRoute: string
  status: VesselStatus
  currentPort: string | null
  destinationPort: string | null
  position: VesselPosition
  speedLossPct: number
  foulingGrade: FoulingGrade
  lastDrydockDate: string
  nextDrydockDue: string
  daysSinceHullClean: number
  maintenanceUrgency: Urgency
  degradationRatePctPerDay: number
  excessFuelCostUsdMtd: number
  nextRecommendedWindow: { start: string; end: string }
}

export interface PortCallEntry {
  port: string
  arrival: string
  departure: string
}

export interface NoonReportEntry {
  date: string
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
  isAnomaly: boolean
  anomalyReason: string | null
}

export interface HullSectionFouling {
  section: 'bow' | 'forward-flat' | 'aft-flat' | 'stern' | 'port-side' | 'starboard-side' | 'propeller' | 'rudder'
  grade: FoulingGrade
}

export interface InspectionEntry {
  id: string
  date: string
  port: string
  surveyor: string
  method: string
  foulingGrade: FoulingGrade
  biofoulingScore: number
  paintBreakdownPct: number
  propellerCondition: string
  cleaningRecommended: string
  notes: string
  hullSections: HullSectionFouling[]
  photoCount: number
  reportUrl: string | null
}

export interface SpeedLossEvent {
  date: string
  type: 'hull_cleaning' | 'propeller_polishing' | 'drydock'
  label: string
}

export interface SpeedLossSeries {
  vessel: { imo: string; name: string; type: string }
  cleanBaseline: { speedKnots: number; source: string }
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
  opportunityCostUsd: number
}

export interface MaintenanceRecommendation {
  action: string
  windowStart: string
  windowEnd: string
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
  date: string
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
  /** Cost of this maintenance event (USD) */
  costUsd: number
}

export interface MaintenanceTypeEffectiveness {
  type: MaintenanceEventType
  /** Number of events of this type */
  eventCount: number
  /** Average fuel improvement (MT/day) */
  avgFuelImprovementMt: number
  /** Average improvement percentage */
  avgImprovementPct: number
  /** Average cost per event */
  avgCostUsd: number
  /** Cost per 1% improvement */
  costPerPctImprovement: number
  /** Star rating 1-5 */
  rating: number
}

export interface PerformanceTimelinePoint {
  date: string
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
    totalMaintenanceCostUsd: number
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
  /** Recommended date window */
  windowStart: string
  windowEnd: string
  /** If deferred: projected extra fuel cost per day (USD) */
  excessFuelCostPerDayUsd: number
  /** Total projected savings from timely intervention (USD) */
  projectedSavingsUsd: number
  /** Reasoning text */
  reasoning: string
  /** Severity: how urgent is this? */
  urgency: 'LOW' | 'MEDIUM' | 'HIGH'
}
