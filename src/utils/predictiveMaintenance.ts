import type { Vessel } from '@/data/mockFleet'

export const SPEED_LOSS_THRESHOLD_PCT = 10

export interface MaintenancePrediction {
  breached: boolean
  daysToBreach: number | null
  recommendedDate: string
  estFuelSavingTDay: number
}

// Hull/propeller cleaning can't happen mid-voyage, only at the next port call
// (per 命題 note: 船舶不是想要馬上維護就可以的) — so the recommendation always
// anchors on vessel.next_hull_clean rather than "do it now".
export function predictMaintenanceWindow(vessel: Vessel): MaintenancePrediction {
  const reports = vessel.noon_reports
  const first = reports[0].speed_loss_pct
  const last = reports[reports.length - 1].speed_loss_pct
  const slopePerDay = (last - first) / (reports.length - 1)

  const breached = last >= SPEED_LOSS_THRESHOLD_PCT
  const daysToBreach = !breached && slopePerDay > 0 ? (SPEED_LOSS_THRESHOLD_PCT - last) / slopePerDay : null

  const estFuelSavingTDay = Number((vessel.fuel_consumption_t_day * (last / 100)).toFixed(1))

  return {
    breached,
    daysToBreach: daysToBreach !== null ? Math.round(daysToBreach) : null,
    recommendedDate: vessel.next_hull_clean,
    estFuelSavingTDay
  }
}
