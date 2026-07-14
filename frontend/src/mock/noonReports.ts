// Synthetic Noon Report / Speed Loss generator.
// Produces a physically-plausible speed-loss sawtooth: loss resets near 0%
// right after each hull cleaning event, then grows roughly linearly (with
// weather noise) until the next cleaning. This lets every downstream view
// (fleet list, vessel overview, speed-loss chart, fuel attribution,
// maintenance advisor) derive consistent numbers from one source of truth.

import { VESSEL_REFS, MAINTENANCE_LOG, type VesselRef } from './reference'
import { addDays, createRng, daysBetween, randRange, MOCK_TODAY } from './seed'
import type { NoonReportEntry, LoadCondition } from '@/types/fleet'

export interface GeneratedSeries {
  vessel: VesselRef
  reports: NoonReportEntry[]
  hullCleaningDates: string[]
  events: { date: string; type: 'hull_cleaning' | 'propeller_polishing'; label: string }[]
}

const SERIES_START = '2022-01-01'

function foulingGradeRate(vesselImo: string): number {
  // %/day growth rate, tuned per vessel so the fleet has variety
  // (matches roughly what the UWI inspection severity progression implies).
  const rateByImo: Record<string, number> = {
    '9786654': 0.014, // YM WELLNESS
    '9695123': 0.021, // YM VICTORY - grows fast, silicone coating underperforming
    '9567788': 0.026, // YM COSMOS - oldest hull, worst fouling growth
    '9832105': 0.017, // YM ESSENCE
    '9701344': 0.023, // YM EVOLUTION
  }
  return rateByImo[vesselImo] ?? 0.018
}

function generateForVessel(vessel: VesselRef): GeneratedSeries {
  const rng = createRng(vessel.imo)
  const events = MAINTENANCE_LOG.filter((m) => m.imo === vessel.imo)
    .map((m) => ({
      date: m.date,
      type: (m.type === 'Hull Cleaning' ? 'hull_cleaning' : 'propeller_polishing') as
        | 'hull_cleaning'
        | 'propeller_polishing',
      label: m.type === 'Hull Cleaning' ? '船體清洗' : '螺旋槳打磨',
    }))
    .sort((a, b) => (a.date < b.date ? -1 : 1))

  const hullCleaningDates = events.filter((e) => e.type === 'hull_cleaning').map((e) => e.date)
  const growthRate = foulingGradeRate(vessel.imo)

  const reports: NoonReportEntry[] = []
  const totalDays = daysBetween(SERIES_START, MOCK_TODAY)
  const stepDays = 2 // one noon report every 2 days keeps dataset light but dense enough for charts

  for (let d = 0; d <= totalDays; d += stepDays) {
    const date = addDays(SERIES_START, d)

    // days since most recent hull cleaning on/before this date
    const priorCleanings = hullCleaningDates.filter((c) => c <= date)
    const lastClean = priorCleanings.length ? priorCleanings[priorCleanings.length - 1] : SERIES_START
    const daysSinceClean = daysBetween(lastClean, date)

    const baseLoss = Math.max(0, growthRate * daysSinceClean)
    const weatherNoise = randRange(rng, -1.1, 1.1)
    const beaufort = Math.max(0, Math.min(9, Math.round(randRange(rng, 0, 6))))
    // rough sea adds transient apparent speed loss on top of fouling trend
    const seaPenalty = beaufort >= 6 ? randRange(rng, 1.5, 3.5) : beaufort >= 4 ? randRange(rng, 0.3, 1.2) : 0

    let speedLossPct = baseLoss + weatherNoise + seaPenalty
    let isAnomaly = false
    let anomalyReason: string | null = null

    // Inject occasional real anomalies (main engine issue / instrumentation) so
    // the anomaly-flagging UI has something meaningful to show.
    const anomalyRoll = rng()
    if (anomalyRoll > 0.985 && beaufort < 4) {
      const extra = randRange(rng, 4, 9)
      speedLossPct += extra
      isAnomaly = true
      anomalyReason = `油耗較同海況基準高 ${Math.round(randRange(rng, 15, 30))}%，疑似主機效率異常`
    }

    speedLossPct = Math.max(-1, speedLossPct)

    const loadCondition: LoadCondition = rng() > 0.45 ? 'laden' : 'ballast'
    const correctedSpeed = vessel.designSpeedKt * (1 - speedLossPct / 100)
    const observedSpeed = correctedSpeed - (seaPenalty > 0 ? seaPenalty * 0.15 : 0) + randRange(rng, -0.3, 0.3)

    const loadFactor = loadCondition === 'laden' ? 1 : 0.86
    const fuelBase = vessel.baselineDailyFuelMt * loadFactor
    // fuel scales roughly with cube of speed ratio, dominated here by fouling-driven power increase
    const fuelFoulingUplift = 1 + speedLossPct / 100 * 1.8
    const fuelConsumptionMt = fuelBase * fuelFoulingUplift * randRange(rng, 0.97, 1.03)

    reports.push({
      date,
      lat: Number(randRange(rng, -10, 40).toFixed(2)),
      lon: Number(randRange(rng, 100, 140).toFixed(2)),
      observedSpeedKt: Number(observedSpeed.toFixed(2)),
      correctedSpeedKt: Number(correctedSpeed.toFixed(2)),
      speedLossPct: Number(speedLossPct.toFixed(2)),
      fuelConsumptionMt: Number(fuelConsumptionMt.toFixed(2)),
      beaufort,
      seaState: Math.min(9, beaufort),
      draftFwd: Number(randRange(rng, vessel.designDraftM - 1.5, vessel.designDraftM).toFixed(2)),
      draftAft: Number(randRange(rng, vessel.designDraftM - 1, vessel.designDraftM + 0.3).toFixed(2)),
      loadCondition,
      isAnomaly,
      anomalyReason,
    })
  }

  return { vessel, reports, hullCleaningDates, events }
}

let cache: Map<string, GeneratedSeries> | null = null

export function getAllSeries(): Map<string, GeneratedSeries> {
  if (!cache) {
    cache = new Map()
    for (const vessel of VESSEL_REFS) {
      cache.set(vessel.imo, generateForVessel(vessel))
    }
  }
  return cache
}

export function getSeriesForVessel(imo: string): GeneratedSeries | undefined {
  return getAllSeries().get(imo)
}
