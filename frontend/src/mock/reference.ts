// Decorative vessel reference data (name, flag, TEU, engine, position...).
// The real backend (sls-api) only knows vessels by id (S1-S12 training,
// S21-S23 prediction) and has none of these presentation fields — no AIS
// feed, no hull/engine spec sheet. Everything below is illustrative flavor
// generated deterministically per vessel_id so the UI's visual design
// (fleet map, spec cards, TEU/flag columns) has something consistent to
// show; it is not derived from any real record. All *analytical* numbers
// (speed loss, fuel consumption, maintenance history) come from the real
// API — see src/mock/api.ts.

import { createRng, randRange } from './seed.ts'

export const TRAINING_VESSEL_IDS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12']
export const PREDICTION_VESSEL_IDS = ['S21', 'S22', 'S23']
export const ALL_VESSEL_IDS = [...TRAINING_VESSEL_IDS, ...PREDICTION_VESSEL_IDS]

export interface VesselRef {
  name: string
  imo: string // holds the real backend vessel_id (e.g. "S1"), not an actual IMO number
  vesselType: string
  teuCapacity: number
  builtYear: number
  flag: string
  classSociety: string
  mainEngineModel: string
  mcrKw: number
  ncrKw: number
  designSpeedKt: number
  designDraftM: number
  designSfocGkWh: number
  hullPaintType: string
  tradeRoute: string
}

const FLAGS = ['Panama', 'Taiwan', 'Liberia', 'Marshall Islands', 'Singapore']
const CLASS_SOCIETIES = ['NK', 'CR', 'BV', 'ABS', 'LR']
const ENGINE_MODELS = ['MAN B&W 9G90ME-C10.5', 'MAN B&W 8G70ME-C9.5', 'MAN B&W 7S80ME-C9', 'WinGD 8X92DF']
const PAINT_TYPES = ['Self-Polishing Copolymer (SPC)', 'Silicone Fouling Release']
const ROUTES = ['Asia-Europe (FE3)', 'Trans-Pacific (PN2)', 'Intra-Asia (CIS)', 'Asia-US East Coast']
const NAME_STEMS = ['WELLNESS', 'VICTORY', 'COSMOS', 'ESSENCE', 'EVOLUTION', 'VOYAGER', 'HORIZON', 'PIONEER', 'HARMONY', 'INTEGRITY', 'ENDEAVOR', 'FRONTIER', 'PRESTIGE', 'SOVEREIGN', 'ASCENT']

function buildVesselRef(vesselId: string, index: number): VesselRef {
  const rng = createRng(`ref-${vesselId}`)
  const isPrediction = PREDICTION_VESSEL_IDS.includes(vesselId)
  const teuCapacity = Math.round(randRange(rng, 6500, 14200) / 100) * 100
  const designSpeedKt = Number(randRange(rng, 19.5, 22.5).toFixed(1))
  return {
    name: `YM ${NAME_STEMS[index % NAME_STEMS.length]}`,
    imo: vesselId,
    vesselType: isPrediction ? 'Container (預測集)' : 'Container',
    teuCapacity,
    builtYear: Math.round(randRange(rng, 2012, 2023)),
    flag: FLAGS[Math.floor(randRange(rng, 0, FLAGS.length))],
    classSociety: CLASS_SOCIETIES[Math.floor(randRange(rng, 0, CLASS_SOCIETIES.length))],
    mainEngineModel: ENGINE_MODELS[Math.floor(randRange(rng, 0, ENGINE_MODELS.length))],
    mcrKw: Math.round(randRange(rng, 27000, 53000)),
    ncrKw: Math.round(randRange(rng, 23000, 45000)),
    designSpeedKt,
    designDraftM: Number(randRange(rng, 12.5, 14.5).toFixed(1)),
    designSfocGkWh: Number(randRange(rng, 163, 178).toFixed(1)),
    hullPaintType: PAINT_TYPES[Math.floor(randRange(rng, 0, PAINT_TYPES.length))],
    tradeRoute: ROUTES[Math.floor(randRange(rng, 0, ROUTES.length))],
  }
}

export const VESSEL_REFS: VesselRef[] = ALL_VESSEL_IDS.map((id, i) => buildVesselRef(id, i))

export interface LiveState {
  lat: number
  lon: number
  headingDeg: number
  speedKt: number
  status: 'underway' | 'moored' | 'anchored'
  currentPort: string | null
  destinationPort: string | null
}

const PORTS = ['Kaohsiung', 'Singapore', 'Colombo', 'Rotterdam', 'Ningbo', 'Fujairah', 'Hamburg', 'Long Beach']

/** Illustrative current position + status, placed along each vessel's decorative trade route. Would come from an AIS feed in production — the real backend has no position data. */
export const VESSEL_LIVE_STATE: Record<string, LiveState> = Object.fromEntries(
  ALL_VESSEL_IDS.map((id) => {
    const rng = createRng(`live-${id}`)
    const statusRoll = rng()
    const status: LiveState['status'] = statusRoll > 0.6 ? 'underway' : statusRoll > 0.3 ? 'moored' : 'anchored'
    const port = PORTS[Math.floor(randRange(rng, 0, PORTS.length))]
    const destPort = PORTS[Math.floor(randRange(rng, 0, PORTS.length))]
    return [
      id,
      {
        lat: Number(randRange(rng, -10, 45).toFixed(2)),
        lon: Number(randRange(rng, 95, 145).toFixed(2)),
        headingDeg: Math.round(randRange(rng, 0, 359)),
        speedKt: status === 'underway' ? Number(randRange(rng, 14, 21).toFixed(1)) : Number(randRange(rng, 0, 0.5).toFixed(1)),
        status,
        currentPort: status === 'underway' ? null : port,
        destinationPort: status === 'underway' ? destPort : null,
      },
    ]
  }),
)
