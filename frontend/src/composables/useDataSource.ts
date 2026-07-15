import { ref } from 'vue'
import type { MaintenanceCorrelationResponse, MaintenanceRecommendation, VesselSummary, SpeedLossSeries, FleetKpis, FuelAttributionResponse } from '@/types/fleet'
import {
  fetchRealMaintenanceCorrelation,
  fetchRealMaintenanceRecommendation,
  fetchRealVesselSummary,
  fetchRealSpeedLoss,
  fetchRealFleetKpis,
  fetchRealFleetVessels,
  getRealShipList,
} from '@/api/adapter'

/**
 * Data source flag — kept for potential future toggle but defaults to true (real data only).
 * Mock vessels (YM WELLNESS etc) are removed; all data comes from competition CSVs.
 */
export const useRealData = ref(true)

/** Returns true if the given identifier is a real competition ship (S1-S23) */
export function isRealShip(imo: string): boolean {
  return getRealShipList().includes(imo)
}

/** Fetch maintenance correlation */
export async function fetchCorrelation(imo: string): Promise<MaintenanceCorrelationResponse | null> {
  return fetchRealMaintenanceCorrelation(imo)
}

/** Fetch maintenance recommendation */
export async function fetchRecommendation(imo: string): Promise<MaintenanceRecommendation | null> {
  return fetchRealMaintenanceRecommendation(imo)
}

/** Fetch vessel summary */
export async function fetchVesselData(imo: string): Promise<VesselSummary | null> {
  return fetchRealVesselSummary(imo)
}

/** Fetch speed loss */
export async function fetchSpeedLossData(imo: string): Promise<SpeedLossSeries | null> {
  return fetchRealSpeedLoss(imo)
}

/** Fetch fleet KPIs */
export async function fetchKpis(): Promise<FleetKpis> {
  return fetchRealFleetKpis()
}

/** Fetch fleet vessels */
export async function fetchVessels(): Promise<VesselSummary[]> {
  return fetchRealFleetVessels()
}

/**
 * Fetch fuel attribution for the voice/chat assistant's fuel_attribution
 * card (useChatOrchestrator.ts) — still a stub returning null. Unlike the
 * web page at /vessels/:imo/fuel-attribution (which calls the real
 * speed-loss-attribution endpoint via services/backend.ts directly), this
 * chat-card code path was never wired to that endpoint.
 */
export async function fetchFuelAttr(_imo: string): Promise<FuelAttributionResponse | null> {
  return null
}
