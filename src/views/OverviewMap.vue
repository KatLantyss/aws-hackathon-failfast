<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useFleetStore } from '@/stores/fleetStore'
import { project, pointToPercent, declutter, toPolylinePoints, VIEWBOX_WIDTH, VIEWBOX_HEIGHT } from '@/utils/geoProjection'
import { worldLandPath } from '@/data/worldLand'
import ImpactBanner from '@/components/common/ImpactBanner.vue'
import IsoBadge from '@/components/common/IsoBadge.vue'
import ShipDetailDrawer from '@/components/fleet/ShipDetailDrawer.vue'

const fleet = useFleetStore()

onMounted(() => fleet.startSimulation())
onUnmounted(() => fleet.stopSimulation())

const statusColor = (status: string) =>
  status === 'critical' ? '#ff5470' : status === 'warning' ? '#ffb020' : '#00e0a0'

// True projected position drives the "real" relative location; declutter()
// only nudges the rendered dot so nearby ships don't fully occlude each
// other, and a leader line shows how far a marker was nudged from the truth.
const displayPositions = computed(() => {
  const truePoints = fleet.vessels
    .filter((v) => fleet.positions[v.id])
    .map((v) => ({ id: v.id, ...project(fleet.positions[v.id]) }))
  const nudged = declutter(truePoints)
  return fleet.vessels.reduce<Record<string, { true: { x: number; y: number }; shown: { x: number; y: number } }>>(
    (acc, v) => {
      const truePos = fleet.positions[v.id]
      if (truePos) acc[v.id] = { true: project(truePos), shown: nudged[v.id] }
      return acc
    },
    {}
  )
})

const markers = computed(() =>
  fleet.vessels.map((v) => {
    const d = displayPositions.value[v.id]
    const shown = d?.shown ?? { x: 0, y: 0 }
    const nudged = d ? Math.hypot(d.shown.x - d.true.x, d.shown.y - d.true.y) > 3 : false
    return {
      vessel: v,
      style: pointToPercent(shown.x, shown.y),
      nudged,
      leaderPoints: d ? `${d.true.x},${d.true.y} ${d.shown.x},${d.shown.y}` : ''
    }
  })
)

const trailPaths = computed(() =>
  fleet.vessels.map((v) => ({
    id: v.id,
    color: statusColor(v.status),
    points: toPolylinePoints(fleet.trails[v.id] ?? [])
  }))
)

const routePaths = computed(() =>
  fleet.vessels.map((v) => ({
    id: v.id,
    points: toPolylinePoints(v.route_points)
  }))
)

const avgSpeedLoss = computed(() => {
  const total = fleet.vessels.reduce((sum, v) => sum + v.speed_loss_pct, 0)
  return (total / fleet.vessels.length).toFixed(1)
})

const criticalCount = computed(() => fleet.vessels.filter((v) => v.status !== 'normal').length)
</script>

<template>
  <div class="pa-6">
    <div class="overview-hero mb-4">
      <div class="d-flex flex-wrap align-start justify-space-between ga-4">
        <div>
          <div class="text-overline text-medium-emphasis">陽明海運 · YANG MING MARINE TRANSPORT</div>
          <div class="text-h6 font-weight-bold">AI 船舶效能分析與節能決策支援系統</div>
          <div class="text-body-2 text-medium-emphasis mt-1">
            整合近 5 年午報（Noon Report）與水下檢查紀錄，自動套用國際標準公式計算船隊效能與節能建議
          </div>
        </div>
        <IsoBadge />
      </div>
    </div>

    <ImpactBanner />

    <v-sheet rounded color="card" class="radar-panel radar-panel--hero" elevation="0" data-tour="radar-panel">
      <div class="radar-header px-4 py-3">
        <div class="d-flex align-center justify-space-between flex-wrap ga-3">
          <div class="d-flex align-center ga-2">
            <v-icon icon="mdi-radar" color="primary" />
            <span class="text-subtitle-2 font-weight-medium">Fleet Radar · 船隊相對位置</span>
          </div>
          <div class="d-flex align-center ga-4 text-caption text-medium-emphasis">
            <span class="legend-dot" style="background: #00e0a0" /> 正常
            <span class="legend-dot" style="background: #ffb020" /> 警示
            <span class="legend-dot" style="background: #ff5470" /> 高風險
          </div>
        </div>

        <div class="radar-stats mt-3">
          <div class="radar-stat">
            <span class="radar-stat-value">{{ fleet.vessels.length }}</span>
            <span class="radar-stat-label">船隊總數（艘）</span>
          </div>
          <div class="radar-stat" data-tour="stat-avg-speedloss">
            <span class="radar-stat-value text-warning">{{ avgSpeedLoss }}%</span>
            <span class="radar-stat-label">平均 Speed Loss</span>
          </div>
          <div class="radar-stat">
            <span class="radar-stat-value text-error">{{ criticalCount }}</span>
            <span class="radar-stat-label">需關注船舶（艘）</span>
          </div>
          <div class="radar-stat">
            <span class="radar-stat-value text-secondary">Live</span>
            <span class="radar-stat-label">模擬座標即時更新</span>
          </div>
        </div>
      </div>

      <div class="radar-ocean">
        <svg :viewBox="`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`" preserveAspectRatio="none" class="radar-svg">
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(0,194,255,0.08)" stroke-width="1" />
            </pattern>
            <radialGradient id="scan" cx="50%" cy="50%" r="70%">
              <stop offset="0%" stop-color="rgba(0,194,255,0.10)" />
              <stop offset="100%" stop-color="rgba(0,194,255,0)" />
            </radialGradient>
            <filter id="landSoften" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="1.4" />
            </filter>
          </defs>

          <!-- Real coastlines (Natural Earth 110m), pre-projected in worldLand.ts through
               the same project() transform as vessel positions, so land never overlaps a route -->
          <path class="landmasses" :d="worldLandPath" filter="url(#landSoften)" />
          <rect width="100%" height="100%" fill="url(#grid)" />
          <rect width="100%" height="100%" fill="url(#scan)" />

          <polyline
            v-for="r in routePaths"
            :key="'route-' + r.id"
            :points="r.points"
            fill="none"
            stroke="rgba(255,255,255,0.10)"
            stroke-width="1.5"
            stroke-dasharray="4 6"
          />

          <polyline
            v-for="t in trailPaths"
            :key="'trail-' + t.id"
            :points="t.points"
            fill="none"
            :stroke="t.color"
            stroke-width="2"
            stroke-linecap="round"
            opacity="0.7"
          />

          <polyline
            v-for="m in markers.filter((m) => m.nudged)"
            :key="'leader-' + m.vessel.id"
            :points="m.leaderPoints"
            fill="none"
            stroke="rgba(255,255,255,0.35)"
            stroke-width="1"
            stroke-dasharray="2 3"
          />
        </svg>

        <button
          v-for="m in markers"
          :key="m.vessel.id"
          class="ship-dot"
          :class="[m.vessel.status, { selected: fleet.selectedVesselId === m.vessel.id }]"
          :data-tour="`ship-${m.vessel.id}`"
          :style="m.style"
          @click="fleet.selectVessel(m.vessel.id)"
        >
          <span class="ship-pulse" :class="m.vessel.status" />
          <v-icon icon="mdi-ferry" size="13" color="white" />
          <span class="ship-tooltip">{{ m.vessel.name }}</span>
        </button>
      </div>
    </v-sheet>

    <ShipDetailDrawer />
  </div>
</template>

<style scoped>
.overview-hero {
  padding: 4px 4px 0;
}

.radar-panel {
  border: 1px solid rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.radar-panel--hero {
  border-color: rgba(0, 194, 255, 0.18);
}

.radar-header {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}

.radar-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
}

.radar-stat {
  display: flex;
  flex-direction: column;
}

.radar-stat-value {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
}

.radar-stat-label {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
}

.radar-ocean {
  position: relative;
  width: 100%;
  aspect-ratio: 1000 / 620;
  background: radial-gradient(ellipse at 50% 40%, #0f2a4a 0%, #06111f 75%);
  overflow: hidden;
}

.radar-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.landmasses {
  fill: rgba(205, 188, 140, 0.13);
  stroke: rgba(205, 188, 140, 0.4);
  stroke-width: 1;
}

.ship-dot {
  position: absolute;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: rgba(10, 22, 40, 0.9);
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-radius: 50%;
  cursor: pointer;
  transition: transform 0.15s ease, border-color 0.15s ease;
  z-index: 2;
}

.ship-dot.normal { border-color: #00e0a0; }
.ship-dot.warning { border-color: #ffb020; }
.ship-dot.critical { border-color: #ff5470; }

.ship-dot:hover {
  transform: translate(-50%, -50%) scale(1.2);
  z-index: 3;
}

.ship-dot.selected {
  border-width: 3px;
  box-shadow: 0 0 0 4px rgba(0, 194, 255, 0.25);
}

.ship-tooltip {
  position: absolute;
  bottom: 130%;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(6, 14, 26, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.15);
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  color: white;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.ship-dot:hover .ship-tooltip,
.ship-dot.selected .ship-tooltip {
  opacity: 1;
}

.ship-pulse {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 16px;
  height: 16px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  opacity: 0.5;
  animation: pulse 1.8s ease-out infinite;
}

.ship-pulse.normal {
  background: #00e0a0;
}
.ship-pulse.warning {
  background: #ffb020;
}
.ship-pulse.critical {
  background: #ff5470;
}

@keyframes pulse {
  0% {
    transform: translate(-50%, -50%) scale(0.6);
    opacity: 0.6;
  }
  100% {
    transform: translate(-50%, -50%) scale(2.2);
    opacity: 0;
  }
}
</style>
