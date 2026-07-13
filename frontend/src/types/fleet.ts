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
