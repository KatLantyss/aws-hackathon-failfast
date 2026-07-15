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
  | 'maintenance_recommendation'
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

export interface ChatSessionMemory {
  pendingEntityResolution: {
    userText: string
    assistantReply: string
    intent: ChatIntent
    factType: ChatFactType | null
    suggestedVesselImo: string | null
  } | null
}

export interface NluRequestBody {
  message: string
  history: ChatHistoryMessage[]
  sessionMemory?: ChatSessionMemory
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
  suggestedQuestions?: string[]
  awaitingVesselFor?: {
    intent: ChatIntent
    factType: ChatFactType | null
    /** A valid vessel ID proposed after an unknown-vessel query; an affirmative reply resumes with this vessel. */
    suggestedVesselImo?: string | null
  } | null
}
