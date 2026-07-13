import type {
  FuelAttributionResponse,
  MaintenanceRecommendation,
  SpeedLossSeries,
  VesselSummary,
} from './fleet.ts'

export type ChatIntent =
  | 'vessel_overview'
  | 'fleet_ranking'
  | 'fuel_attribution'
  | 'compare_vessels'
  | 'single_fact'
  | 'follow_up'
  | 'out_of_scope'

export type ChatFactType =
  | 'last_hull_cleaning'
  | 'last_drydock'
  | 'next_drydock'
  | 'current_speed_loss'
  | 'fouling_grade'

export interface ChatHistoryMessage {
  role: 'user' | 'assistant'
  content: string
}

/** Raw structured output from the /api/nlu Claude tool call — intent + params only, never a data conclusion. */
export interface NluResult {
  intent: ChatIntent
  vessels: { imo: string; name: string }[]
  vesselNotFound: boolean
  vesselGuess: string | null
  factType: ChatFactType | null
  clarifyingNote: string
  outOfScopeExamples: string[] | null
}

export interface NluRequestBody {
  message: string
  history: ChatHistoryMessage[]
}

export type ChatCardSpec =
  | { type: 'gauge'; vessel: VesselSummary }
  | { type: 'speedLoss'; vessel: VesselSummary; series: SpeedLossSeries }
  | { type: 'maintenance'; vessel: VesselSummary; data: MaintenanceRecommendation }
  | { type: 'fuelWaterfall'; vessel: VesselSummary; data: FuelAttributionResponse }
  | { type: 'ranking'; vessels: VesselSummary[] }
  | {
      type: 'compare'
      a: { vessel: VesselSummary; series: SpeedLossSeries }
      b: { vessel: VesselSummary; series: SpeedLossSeries }
    }

export interface ChatTurn {
  id: string
  userText: string
  intent: ChatIntent
  replyText: string
  cards: ChatCardSpec[]
  vesselImo: string | null
  vesselName: string | null
  breadcrumbLabel: string
  /** Set when this turn is a "which vessel do you mean?" clarifying question — the next turn resumes this intent once a vessel resolves, instead of treating a bare vessel name as an unrelated query. */
  awaitingVesselFor?: { intent: ChatIntent; factType: ChatFactType | null } | null
}
