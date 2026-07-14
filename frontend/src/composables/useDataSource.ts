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

/** Fetch fuel attribution — not yet backed by real API, returns null */
export async function fetchFuelAttr(_imo: string): Promise<FuelAttributionResponse | null> {
  return null
}

/** Fetch noon reports — returns null (backend has the data but we haven't wired the display yet) */
export async function fetchNoonReportsData(_imo: string): Promise<null> {
  return null
}

/** Fetch inspections — returns empty array (no UWI detail data in competition dataset) */
export async function fetchInspectionsData(_imo: string): Promise<never[]> {
  return []
}
