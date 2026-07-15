// Thin typed client for the deployed Ship Performance Analysis API
// (sls-api Lambda + API Gateway + DynamoDB). See sls-api/API.md for the
// authoritative endpoint docs — response shapes here are verified against
// the live deployment, which has drifted from that doc in places
// (speed-loss, speed-loss-attribution, fleet/ranking).
//
// Field names are kept snake_case / vessel_id (not imo) to make it obvious
// at a glance which values are raw backend data vs. frontend-adapted
// (src/api/adapter.ts does the adaptation into src/types/fleet.ts shapes).

const BASE_URL = (import.meta.env?.VITE_BACKEND_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class BackendError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new BackendError(body?.error ?? `Backend request failed: ${res.status} ${path}`)
  }
  return res.json() as Promise<T>
}

export type BackendVesselType = 'training' | 'prediction'

export interface BackendVesselListItem {
  vessel_id: string
  type: BackendVesselType
}

export interface BackendVesselList {
  vessels: BackendVesselListItem[]
  total: number
}

export interface BackendVesselDetail {
  vessel_id: string
  total_records: number
  avg_speed_kn: number
  avg_consumption: number
  avg_stw_kn: number
  voyage_range: { min: number; max: number }
}

export interface BackendNoonReport {
  vessel_id: string
  noon_day: number
  voyage: number
  avg_speed_kn: number | null
  speed_through_water: number | null
  me_rpm: number | null
  fore_draft: number | null
  aft_draft: number | null
  cargo_on_board: number | null
  wind_scale: number | null
  sea_height: number | null
  horse_power: number | null
  me_consumption: number | null
  total_consump: number | null
  sfoc: number | null
  me_slip: number | null
}

export interface BackendNoonReportsResponse {
  vessel_id: string
  count: number
  records: BackendNoonReport[]
}

export interface BackendSpeedLossSlipPoint {
  noon_day: number
  voyage: number
  slip_pct: number
  wind_scale: number | null
  hours_full_speed: number | null
}

export interface BackendSpeedLossIsoPoint {
  noon_day: number
  voyage: number
  rpm: number | null
  stw: number | null
  ref_stw: number | null
  speed_loss_kn: number | null
  wind_scale: number | null
}

export interface BackendSpeedLoss {
  vessel_id: string
  method: string
  slip_summary: { avg_slip_pct: number; valid_records: number; total_records: number }
  slip_timeline: BackendSpeedLossSlipPoint[]
  iso_summary: {
    avg_speed_loss_kn: number
    baseline_records: number
    calm_records: number
    rpm_baseline: Record<string, unknown>
  }
  iso_timeline: BackendSpeedLossIsoPoint[]
}

export type SpeedLossAttributionCategory = 'hull+propeller' | 'hull' | 'propeller' | 'inspection_only' | 'other'

export interface BackendSpeedLossAttributionEvent {
  event_type: string
  event_day: number
  category: SpeedLossAttributionCategory
  physical_intervention: boolean
  slip_before_pct: number
  slip_after_pct: number
  slip_delta_pct: number
  notes: string
}

export interface BackendSpeedLossAttribution {
  vessel_id: string
  method: string
  summary: Partial<Record<SpeedLossAttributionCategory, number>>
  event_attributions: BackendSpeedLossAttributionEvent[]
  weather_timeline: { noon_day: number; diff_stw_sog: number }[]
}

export interface BackendMaintenanceEvent {
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

export interface BackendMaintenanceEventsResponse {
  vessel_id: string
  total: number
  events: BackendMaintenanceEvent[]
}

export interface BackendMaintenanceRecommendation {
  vessel_id: string
  days_since_maintenance: number
  avg_me_slip_pct: number
  recommendation: 'URGENT' | 'ROUTINE'
  recommended_type: 'DD' | 'UWC'
  reason: string
  last_maintenance: { event_type: string; event_day: number } | null
}

export interface BackendFleetRankingItem {
  vessel_id: string
  avg_slip_pct: number
  recent_90d_slip_pct: number
  slip_trend: number
  avg_consumption_mt: number
  valid_slip_records: number
  total_records: number
  rank: number
}

export interface BackendFleetRanking {
  fleet_ranking: BackendFleetRankingItem[]
  total: number
}

// Field names below are exactly what handler.py's predict_fuel() reads from
// the request body (backend-api/handler.py ~line 1141-1155) — UPPERCASE
// A-class column names from vt_fd.csv, not the frontend's usual snake_case.
// `noon_day` (recommended usage) makes the backend look up a real DynamoDB
// row for every field not explicitly overridden here; without it, unlisted
// features fall back to hardcoded defaults (e.g. WIND_SCALE=3.0), and
// days_since_hull_clean/days_since_prop_polish can't be computed from real
// maintenance history at all.
export interface BackendFuelPredictionInput {
  vessel_id: string
  noon_day?: number
  AVG_SPEED?: number
  SPEED_THROUGH_WATER?: number
  WIND_SCALE?: number
  WIND_SPEED?: number
  SEA_HEIGHT?: number
  SWELL_HEIGHT?: number
  SEA_WATER_TEMP?: number
  WATER_DEPTH?: number
  FORE_DRAFT?: number
  AFTER_DRAFT?: number
  MID_DRAFT?: number
  HOURS_FULL_SPEED?: number
  DIFF_STW_SOG_SLIP?: number
  FULL_SPD_STW_SLIP?: number
}

export interface BackendFuelPredictionResult {
  vessel_id: string
  noon_day: number | null
  model: string
  input_used: {
    avg_speed_kn: number
    stw_kn: number
    wind_scale: number
    sea_height: number
    fore_draft: number
    aft_draft: number
    hours_full_speed: number
    days_since_hull_clean: number
    days_since_prop_polish: number
  }
  predicted_consumption_mt: number
  /** Reflects performing UWC+PP (hull cleaning + propeller polish) right now (days_since=0) — not a speed change. */
  counterfactual_uwc_pp: {
    description: string
    predicted_consumption_mt: number
    fuel_saving_mt_per_day: number
    saving_pct: number
    est_annual_saving_mt: number
    est_annual_saving_usd: number
  }
}

export function getHealth() {
  return request<{ status: string; vessel_table: string; maint_table: string }>('/health')
}

export function getVessels() {
  return request<BackendVesselList>('/api/v1/vessels')
}

export function getVesselDetail(vesselId: string) {
  return request<BackendVesselDetail>(`/api/v1/vessels/${encodeURIComponent(vesselId)}`)
}

export function getNoonReports(vesselId: string, opts: { limit?: number; voyage?: number } = {}) {
  const params = new URLSearchParams()
  params.set('limit', String(opts.limit ?? 5000))
  if (opts.voyage != null) params.set('voyage', String(opts.voyage))
  return request<BackendNoonReportsResponse>(`/api/v1/vessels/${encodeURIComponent(vesselId)}/noon-reports?${params}`)
}

export function getSpeedLoss(vesselId: string) {
  return request<BackendSpeedLoss>(`/api/v1/vessels/${encodeURIComponent(vesselId)}/speed-loss`)
}

export function getSpeedLossAttribution(vesselId: string) {
  return request<BackendSpeedLossAttribution>(`/api/v1/vessels/${encodeURIComponent(vesselId)}/speed-loss-attribution`)
}

export function getMaintenanceEvents(vesselId: string) {
  return request<BackendMaintenanceEventsResponse>(`/api/v1/vessels/${encodeURIComponent(vesselId)}/maintenance-events`)
}

export function getMaintenanceRecommendation(vesselId: string) {
  return request<BackendMaintenanceRecommendation>(`/api/v1/vessels/${encodeURIComponent(vesselId)}/maintenance-recommendation`)
}

export function getFleetRanking() {
  return request<BackendFleetRanking>('/api/v1/fleet/ranking')
}

export function predictFuelConsumption(input: BackendFuelPredictionInput) {
  return request<BackendFuelPredictionResult>('/api/v1/predict/fuel-consumption', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}
