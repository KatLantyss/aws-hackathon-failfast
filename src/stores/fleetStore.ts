import { defineStore } from 'pinia'
import { vessels, interpolateRoute, type Vessel, type Waypoint } from '@/data/mockFleet'

interface FleetState {
  vessels: Vessel[]
  positions: Record<string, Waypoint>
  trails: Record<string, Waypoint[]>
  progress: Record<string, number>
  selectedVesselId: string | null
  detailOpen: boolean
  tickerHandle: ReturnType<typeof setInterval> | null
}

const TRAIL_LENGTH = 10

export const useFleetStore = defineStore('fleet', {
  state: (): FleetState => ({
    vessels,
    positions: {},
    trails: Object.fromEntries(vessels.map((v) => [v.id, []])),
    progress: Object.fromEntries(vessels.map((v, i) => [v.id, i / vessels.length])),
    selectedVesselId: null,
    detailOpen: false,
    tickerHandle: null
  }),
  getters: {
    selectedVessel(state): Vessel | null {
      return state.vessels.find((v) => v.id === state.selectedVesselId) ?? null
    }
  },
  actions: {
    startSimulation() {
      if (this.tickerHandle) return
      this.tick()
      this.tickerHandle = setInterval(() => this.tick(), 1500)
    },
    stopSimulation() {
      if (this.tickerHandle) clearInterval(this.tickerHandle)
      this.tickerHandle = null
    },
    tick() {
      for (const vessel of this.vessels) {
        const speedFactor = vessel.speed_knots / 4000
        this.progress[vessel.id] = (this.progress[vessel.id] ?? 0) + speedFactor
        const nextPos = interpolateRoute(vessel.route_points, this.progress[vessel.id])
        this.positions[vessel.id] = nextPos
        const trail = this.trails[vessel.id] ?? []
        trail.push(nextPos)
        if (trail.length > TRAIL_LENGTH) trail.shift()
        this.trails[vessel.id] = trail
      }
    },
    selectVessel(id: string) {
      this.selectedVesselId = id
      this.detailOpen = true
    },
    closeDetail() {
      this.detailOpen = false
    }
  }
})
