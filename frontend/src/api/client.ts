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

export interface ApiSpeedLossPoint {
  noon_day: number
  voyage: number
  rpm: number
  stw: number
  ref_stw: number
  speed_loss_kn: number
  wind_scale: number
}

export interface ApiSpeedLossResponse {
  vessel_id: string
  speed_loss_data: ApiSpeedLossPoint[]
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
  avg_slip_pct: number | null
  recent_90d_slip_pct: number | null
  slip_trend: number | null
  avg_consumption_mt: number | null
  urgency: VesselUrgency
  days_since_maintenance: number | null
  days_since_hull_clean: number | null
  excess_fuel_cost_usd_per_day: number
  lat: number
  lon: number
  heading_deg: number
  speed_kt: number
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

export function fetchApiFleetSummary(): Promise<ApiFleetSummary> {
  return get('/api/v1/fleet/summary')
}
