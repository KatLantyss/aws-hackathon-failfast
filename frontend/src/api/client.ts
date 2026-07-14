/**
 * API client for the real backend endpoints.
 * Base URL must be set via VITE_BACKEND_BASE_URL env variable.
 * Local dev: http://localhost:8000 (set in .env.local, started by make dev)
 */

const BASE_URL = (import.meta.env.VITE_BACKEND_BASE_URL as string | undefined)?.replace(/\/$/, '')
if (!BASE_URL) throw new Error('VITE_BACKEND_BASE_URL is not set. Add it to .env.local')

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`)
  return res.json()
}

// ─── Response types from backend ──────────────────────────────────────────────

export interface ApiVesselList {
  vessels: { vessel_id: string; type: 'training' | 'prediction' }[]
  total: number
}

export interface ApiVesselDetail {
  vessel_id: string
  total_records: number
  avg_speed_kn: number
  avg_consumption: number
  avg_stw_kn: number
  voyage_range: { min: number; max: number }
}

export interface ApiSpeedLossIsoPoint {
  noon_day: number
  voyage: number
  rpm: number | null
  stw: number | null
  ref_stw: number | null
  speed_loss_kn: number | null
  wind_scale: number | null
}

export interface ApiSpeedLossSlipPoint {
  noon_day: number
  voyage: number
  slip_pct: number
  wind_scale: number | null
  hours_full_speed: number | null
}

export interface ApiSpeedLossResponse {
  vessel_id: string
  method: string
  slip_summary: {
    avg_slip_pct: number | null
    valid_records: number
    total_records: number
  }
  slip_timeline: ApiSpeedLossSlipPoint[]
  iso_summary: {
    avg_speed_loss_kn: number | null
    baseline_records: number
    calm_records: number
  }
  iso_timeline: ApiSpeedLossIsoPoint[]
}

export interface ApiMaintenanceEvent {
  vessel_id: string
  event_day: number
  event_type: string
  propeller_condition: string | null
  hull_fouling_type: string | null
  hull_coating_condition: string | null
  cavitation_found: string | null
  draft_fwd_m: number | null
  draft_aft_m: number | null
}

export interface ApiMaintenanceEventsResponse {
  vessel_id: string
  events: ApiMaintenanceEvent[]
  total: number
}

export interface ApiFleetRankingEntry {
  vessel_id: string
  avg_slip_pct: number
  recent_90d_slip_pct: number
  slip_trend: number
  avg_consumption_mt: number
  valid_slip_records: number
  total_records: number
  rank: number
}

export interface ApiFleetRankingResponse {
  fleet_ranking: ApiFleetRankingEntry[]
  total: number
}

export interface ApiNoonReport {
  vessel_id: string
  noon_day: number
  voyage: number
  avg_speed_kn: number
  speed_through_water: number
  me_rpm: number
  fore_draft: number
  aft_draft: number
  cargo_on_board: number
  wind_scale: number
  sea_height: number | null
  horse_power: number | null
  me_consumption: number | null
  total_consump: number | null
  sfoc: number | null
  me_slip: number
}

export interface ApiNoonReportsResponse {
  vessel_id: string
  noon_reports: ApiNoonReport[]
  total: number
}

// ─── API functions ────────────────────────────────────────────────────────────

export function fetchApiVessels(): Promise<ApiVesselList> {
  return get('/api/v1/vessels')
}

export function fetchApiVesselDetail(vesselId: string): Promise<ApiVesselDetail> {
  return get(`/api/v1/vessels/${vesselId}`)
}

export function fetchApiSpeedLoss(vesselId: string): Promise<ApiSpeedLossResponse> {
  return get(`/api/v1/vessels/${vesselId}/speed-loss`)
}

export function fetchApiMaintenanceEvents(vesselId: string): Promise<ApiMaintenanceEventsResponse> {
  return get(`/api/v1/vessels/${vesselId}/maintenance-events`)
}

export function fetchApiFleetRanking(): Promise<ApiFleetRankingResponse> {
  return get('/api/v1/fleet/ranking')
}

export function fetchApiNoonReports(vesselId: string): Promise<ApiNoonReportsResponse> {
  return get(`/api/v1/vessels/${vesselId}/noon-reports`)
}

// ─── Fleet Summary ────────────────────────────────────────────────────────────

export type VesselUrgency = 'LOW' | 'MEDIUM' | 'HIGH'

export interface ApiFleetSummaryVessel {
  vessel_id: string
  type: 'training' | 'prediction'
  ship_class: string
  // slip / speed loss
  avg_slip_pct: number | null
  recent_90d_slip_pct: number | null
  slip_trend: number | null
  valid_slip_records: number | null
  // performance
  avg_speed_kn: number | null
  avg_stw_kn: number | null
  avg_rpm: number | null
  avg_consumption_mt: number | null
  avg_sfoc: number | null
  avg_horse_power: number | null
  avg_me_slip_pct: number | null
  avg_load_pct: number | null
  // environment
  avg_wind_scale: number | null
  avg_sea_height_m: number | null
  avg_sea_water_temp_c: number | null
  // loading
  avg_fore_draft_m: number | null
  avg_aft_draft_m: number | null
  avg_mid_draft_m: number | null
  avg_cargo_on_board_mt: number | null
  avg_displacement_mt: number | null
  // voyage coverage
  total_records: number
  total_voyages: number
  day_range_min: number | null
  day_range_max: number | null
  data_span_days: number | null
  // maintenance
  total_maint_events: number | null
  last_event_type: string | null
  last_event_day: number | null
  days_since_maintenance: number | null
  days_since_hull_clean: number | null
  last_hull_clean_type: string | null
  last_hull_clean_day: number | null
  last_prop_polish_day: number | null
  days_since_prop_polish: number | null
  // cost
  excess_fuel_cost_usd_per_day: number
  // urgency
  urgency: VesselUrgency
  // position
  lat: number
  lon: number
  heading_deg: number
  speed_kt: number
  // meta
  last_updated: string
  rank: number | null
}

export interface ApiFleetSummary {
  total_vessels: number
  training_vessels: number
  prediction_vessels: number
  pending_maintenance: number
  avg_fleet_slip_pct: number | null
  total_excess_fuel_cost_usd_per_day: number
  worst_vessel: {
    vessel_id: string
    avg_slip_pct: number
    urgency: VesselUrgency
  } | null
  per_vessel: ApiFleetSummaryVessel[]
}

// fetchRealFleetKpis() and fetchRealFleetVessels() (adapter.ts) both call this
// independently, and views like FleetOverview.vue call both on mount — coalesce
// concurrent calls so a single page load doesn't fire the request twice.
let fleetSummaryInFlight: Promise<ApiFleetSummary> | null = null

export function fetchApiFleetSummary(): Promise<ApiFleetSummary> {
  if (fleetSummaryInFlight) return fleetSummaryInFlight
  fleetSummaryInFlight = get<ApiFleetSummary>('/api/v1/fleet/summary').finally(() => {
    fleetSummaryInFlight = null
  })
  return fleetSummaryInFlight
}

// ─── Maintenance Recommendation ───────────────────────────────────────────────

export interface ApiCostBenefitPoint {
  deferral_days: number
  projected_slip_pct: number
  cumulative_excess_fuel_cost_usd: number
}

export interface ApiMaintenanceRecommendation {
  vessel_id: string
  days_since_maintenance: number
  avg_me_slip_pct: number | null
  avg_consumption_mt: number | null
  degradation_rate_pct_per_day: number
  fuel_price_usd_per_mt: number
  recommendation: 'URGENT' | 'ROUTINE'
  recommended_type: 'DD' | 'UWC'
  reason: string
  last_maintenance: { event_type: string | null; event_day: number } | null
  curve: ApiCostBenefitPoint[]
}

export function fetchApiMaintenanceRecommendation(vesselId: string): Promise<ApiMaintenanceRecommendation> {
  return get(`/api/v1/vessels/${vesselId}/maintenance-recommendation`)
}
