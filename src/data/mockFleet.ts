export interface Waypoint {
  lng: number
  lat: number
}

export interface NoonReportRow {
  date: string
  WIND_SCALE: number
  HOURS_FULL_SPEED: number
  ME_FULLSPEED_CONSUMP_VLSFO: number
  speed_loss_pct: number
}

export interface Vessel {
  id: string
  name: string
  type: string
  route: string
  route_points: Waypoint[]
  speed_knots: number
  speed_loss_pct: number
  fuel_consumption_t_day: number
  status: 'normal' | 'warning' | 'critical'
  last_hull_clean: string
  next_hull_clean: string
  crew: number
  noon_reports: NoonReportRow[]
}

// Daily FOC = ME_FULLSPEED_CONSUMP_VLSFO / HOURS_FULL_SPEED * 24 (per 命題說明-2)
export function computeDailyFoc(row: NoonReportRow): number {
  return (row.ME_FULLSPEED_CONSUMP_VLSFO / row.HOURS_FULL_SPEED) * 24
}

// Generates 14 days of noon-report-shaped rows, already filtered to WIND_SCALE <= 4
// and HOURS_FULL_SPEED >= 22 as the competition dataset requires. Fuel burn is modeled
// as rising with speed_loss_pct, since hull/propeller fouling forces higher ME output
// to hold the same speed.
function generateNoonReports(finalSpeedLossPct: number, finalFuelConsumptionTDay: number): NoonReportRow[] {
  const baseFoc = finalFuelConsumptionTDay / (1 + finalSpeedLossPct / 100)
  return Array.from({ length: 14 }, (_, i) => {
    const speedLoss = Math.max(0, finalSpeedLossPct - 3 + Math.sin(i / 2) * 1.2 + i * 0.18)
    const hoursFullSpeed = 22 + (i % 3) * 0.5
    const dailyFoc = baseFoc * (1 + speedLoss / 100)
    const meFullspeedConsumpVlsfo = (dailyFoc * hoursFullSpeed) / 24
    const day = new Date()
    day.setDate(day.getDate() - (13 - i))
    return {
      date: day.toISOString().slice(0, 10),
      WIND_SCALE: 1 + (i % 4),
      HOURS_FULL_SPEED: Number(hoursFullSpeed.toFixed(1)),
      ME_FULLSPEED_CONSUMP_VLSFO: Number(meFullspeedConsumpVlsfo.toFixed(1)),
      speed_loss_pct: Number(speedLoss.toFixed(1))
    }
  })
}

export const vessels: Vessel[] = [
  {
    id: 'ym-wellness',
    name: 'YM WELLNESS',
    type: '貨櫃輪 · 14,000 TEU',
    route: '亞洲 → 歐洲 (FE-EU)',
    route_points: [
      { lng: 121.7, lat: 25.1 },
      { lng: 114.1, lat: 22.3 },
      { lng: 103.8, lat: 1.3 },
      { lng: 80.2, lat: 6.9 },
      { lng: 55.3, lat: 12.5 },
      { lng: 32.5, lat: 29.9 },
      { lng: 14.2, lat: 36.8 },
      { lng: 4.4, lat: 51.9 }
    ],
    speed_knots: 18.4,
    speed_loss_pct: 6.2,
    fuel_consumption_t_day: 142,
    status: 'warning',
    last_hull_clean: '2026-04-12',
    next_hull_clean: '2026-08-20',
    crew: 22,
    noon_reports: generateNoonReports(6.2, 142)
  },
  {
    id: 'ym-mandate',
    name: 'YM MANDATE',
    type: '貨櫃輪 · 11,000 TEU',
    route: '亞洲 → 美西 (TP)',
    route_points: [
      { lng: 121.5, lat: 24.9 },
      { lng: 128.6, lat: 30.4 },
      { lng: 155.0, lat: 35.0 },
      { lng: -178.0, lat: 40.0 },
      { lng: -150.0, lat: 42.0 },
      { lng: -122.4, lat: 37.8 }
    ],
    speed_knots: 20.1,
    speed_loss_pct: 2.1,
    fuel_consumption_t_day: 118,
    status: 'normal',
    last_hull_clean: '2026-06-02',
    next_hull_clean: '2026-11-15',
    crew: 21,
    noon_reports: generateNoonReports(2.1, 118)
  },
  {
    id: 'ym-credibility',
    name: 'YM CREDIBILITY',
    type: '貨櫃輪 · 20,000 TEU',
    route: '亞洲 → 澳洲 (AAX)',
    route_points: [
      { lng: 121.3, lat: 24.5 },
      { lng: 114.5, lat: 15.0 },
      { lng: 108.9, lat: 2.1 },
      { lng: 113.8, lat: -8.5 },
      { lng: 130.8, lat: -20.5 },
      { lng: 151.2, lat: -33.9 }
    ],
    speed_knots: 15.7,
    speed_loss_pct: 11.8,
    fuel_consumption_t_day: 176,
    status: 'critical',
    last_hull_clean: '2025-11-30',
    next_hull_clean: '2026-07-25',
    crew: 24,
    noon_reports: generateNoonReports(11.8, 176)
  },
  {
    id: 'ym-utmost',
    name: 'YM UTMOST',
    type: '貨櫃輪 · 8,500 TEU',
    route: '基隆 → 高雄 → 東南亞 (SEA)',
    route_points: [
      { lng: 121.7, lat: 25.1 },
      { lng: 120.3, lat: 22.6 },
      { lng: 114.1, lat: 22.3 },
      { lng: 106.7, lat: 10.8 },
      { lng: 103.8, lat: 1.3 }
    ],
    speed_knots: 17.9,
    speed_loss_pct: 4.5,
    fuel_consumption_t_day: 96,
    status: 'normal',
    last_hull_clean: '2026-05-18',
    next_hull_clean: '2026-10-02',
    crew: 19,
    noon_reports: generateNoonReports(4.5, 96)
  }
]

export function interpolateRoute(points: Waypoint[], t: number): Waypoint {
  const segments = points.length - 1
  const pos = (t % 1) * segments
  const i = Math.min(Math.floor(pos), segments - 1)
  const frac = pos - i
  const a = points[i]
  const b = points[i + 1]
  return {
    lng: a.lng + (b.lng - a.lng) * frac,
    lat: a.lat + (b.lat - a.lat) * frac
  }
}
