<script setup lang="ts">
// Ambient brand scene — isometric Yang Ming container ship.
//
// Reinterprets the Yang Ming annual key visual: a bold isometric container
// vessel with real dimensional depth (each container = shaded top + two
// sides), near-black hull with brand-red waterline, white bridge + red
// funnel, "YANG MING" along the hull. Containers "load in" from above with a
// staggered drop; the ship gently bobs; a mast light blinks. Degrades to a
// static composition under prefers-reduced-motion. Anchored bottom-right and
// read faintly through the frosted-glass panels.
import { computed } from 'vue'

// ---- isometric projection (X = ship length, Y = beam, Z = height) -------
const S = 4
const AX = Math.cos(Math.PI / 6) // 0.866
const AY = Math.sin(Math.PI / 6) // 0.5

function projN(x: number, y: number, z: number): [number, number] {
  return [(x - y) * AX * S, (x + y) * AY * S - z * S]
}
function p(x: number, y: number, z: number): string {
  const [sx, sy] = projN(x, y, z)
  return `${sx.toFixed(1)},${sy.toFixed(1)}`
}
function shade(hex: string, f: number): string {
  const n = parseInt(hex.slice(1), 16)
  const r = Math.min(255, Math.round(((n >> 16) & 255) * f))
  const g = Math.min(255, Math.round(((n >> 8) & 255) * f))
  const b = Math.min(255, Math.round((n & 255) * f))
  return `rgb(${r},${g},${b})`
}

interface Face {
  pts: string
  fill: string
}
const EDGE = 'rgba(15,15,18,0.32)'

function box(x: number, y: number, z: number, w: number, d: number, h: number, base: string): Face[] {
  const top = `${p(x, y, z + h)} ${p(x + w, y, z + h)} ${p(x + w, y + d, z + h)} ${p(x, y + d, z + h)}`
  const sideX = `${p(x + w, y, z)} ${p(x + w, y + d, z)} ${p(x + w, y + d, z + h)} ${p(x + w, y, z + h)}`
  const sideY = `${p(x, y + d, z)} ${p(x + w, y + d, z)} ${p(x + w, y + d, z + h)} ${p(x, y + d, z + h)}`
  return [
    { pts: sideX, fill: shade(base, 0.72) },
    { pts: sideY, fill: shade(base, 0.84) },
    { pts: top, fill: shade(base, 1.16) },
  ]
}

const HULL_BLACK = '#1e1e24'
const BRAND_RED = '#d7191f'
const DECK = '#33333a'
const BRIDGE = '#e9e6de'
const PAL = ['#c53b30', '#d98a3a', '#3e7c74', '#c9a24a', '#3f6d8c', '#e6e2d8', '#9c4a34', '#b3ada0']

const BEAM = 54
const H = [
  [4, 4, 3],
  [4, 3, 4],
  [3, 4, 4],
  [4, 4, 4],
  [3, 4, 3],
  [3, 3, 2],
]
const CDX = 20 // container length (along X)
const CDY = 14 // container beam (along Y)
const CH = 9

// hull + stern superstructure + funnel (static base)
const hullFaces = computed<Face[]>(() => {
  const out: Face[] = []
  out.push(...box(0, 0, -24, 168, BEAM, 8, BRAND_RED)) // red waterline stripe
  out.push(...box(0, 0, -16, 168, BEAM, 16, HULL_BLACK)) // black hull body
  out.push(...box(4, 6, 0, 18, 42, 40, BRIDGE)) // bridge (stern)
  out.push(...box(8, 20, 40, 12, 12, 16, BRAND_RED)) // funnel
  out.push(...box(8, 20, 56, 12, 12, 3, HULL_BLACK)) // funnel cap
  return out
})

// containers, each its own group for a staggered drop-in
interface Cargo {
  faces: Face[]
  delay: number
}
const cargoGroups = computed<Cargo[]>(() => {
  const cells: { x: number; y: number; z: number; g: number; base: string }[] = []
  for (let bay = 0; bay < H.length; bay++) {
    for (let i = 0; i < 3; i++) {
      const stack = H[bay][i]
      for (let g = 0; g < stack; g++) {
        cells.push({
          x: 30 + bay * 23,
          y: 6 + i * 16,
          z: g * CH,
          g,
          base: PAL[(i * 2 + bay + g) % PAL.length],
        })
      }
    }
  }
  cells.sort((a, b) => a.x + a.y + a.z - (b.x + b.y + b.z))
  return cells.map((c) => ({
    faces: box(c.x, c.y, c.z, CDX, CDY, CH, c.base),
    delay: c.g * 300 + (c.x + c.y) * 1.4 + 90,
  }))
})

// pointed bow at the forward (high-X) end, drawn in front
const bowFaces = computed<Face[]>(() => {
  const apx = 210
  const cy = BEAM / 2
  return [
    { pts: `${p(168, BEAM, 0)} ${p(apx, cy, 0)} ${p(apx, cy, -16)} ${p(168, BEAM, -16)}`, fill: shade(HULL_BLACK, 0.84) },
    { pts: `${p(168, BEAM, -16)} ${p(apx, cy, -16)} ${p(apx, cy, -24)} ${p(168, BEAM, -24)}`, fill: shade(BRAND_RED, 0.84) },
    { pts: `${p(168, 0, 0)} ${p(168, BEAM, 0)} ${p(apx, cy, 0)}`, fill: shade(DECK, 1.05) },
  ]
})

const mastLight = computed(() => {
  const [x, y] = projN(14, 26, 78)
  return { x, y }
})

// "YANG MING" along the down-left hull side (+Y face), reading toward the bow
const hullTextTransform = computed(() => {
  const [ex, ey] = projN(52, BEAM, -9)
  return `matrix(${AX},${AY},0,1,${ex},${ey})`
})
</script>

<template>
  <div class="ship-scene" aria-hidden="true">
    <svg viewBox="0 0 1100 780" preserveAspectRatio="xMaxYMax meet" class="h-full w-full">
      <g transform="translate(360,168)">
        <g class="ship-bob">
          <polygon
            v-for="(f, idx) in hullFaces"
            :key="'hull-' + idx"
            :points="f.pts"
            :fill="f.fill"
            :stroke="EDGE"
            stroke-width="0.5"
            stroke-linejoin="round"
          />

          <g
            v-for="(c, ci) in cargoGroups"
            :key="'cargo-' + ci"
            class="cargo"
            :style="{ animationDelay: c.delay + 'ms' }"
          >
            <polygon
              v-for="(f, fi) in c.faces"
              :key="fi"
              :points="f.pts"
              :fill="f.fill"
              :stroke="EDGE"
              stroke-width="0.5"
              stroke-linejoin="round"
            />
          </g>

          <polygon
            v-for="(f, idx) in bowFaces"
            :key="'bow-' + idx"
            :points="f.pts"
            :fill="f.fill"
            :stroke="EDGE"
            stroke-width="0.5"
            stroke-linejoin="round"
          />

          <text :transform="hullTextTransform" class="ship-scene__hull-text" font-size="15">YANG MING</text>

          <circle :cx="mastLight.x" :cy="mastLight.y" r="2.6" fill="#ffffff" class="ship-scene__light" />
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.ship-scene {
  position: fixed;
  right: -30px;
  bottom: -16px;
  width: min(62vw, 1020px);
  height: min(44vw, 720px);
  z-index: 1; /* floats above the wave field (z-0), below content (z-2) */
  pointer-events: none;
  opacity: 0.92;
  /* Keep the ship's own geometry fully opaque (so ocean dots never show
     through the hull/containers) — only the empty margin beyond the vessel
     fades, for a soft blend into the page rather than a hard box edge. */
  -webkit-mask-image: radial-gradient(140% 140% at 100% 100%, black 70%, transparent 100%);
  mask-image: radial-gradient(140% 140% at 100% 100%, black 70%, transparent 100%);
}

.ship-scene__hull-text {
  font-family: var(--font-display), sans-serif;
  font-weight: 700;
  letter-spacing: 0.12em;
  fill: #f5f3ee;
}

/* container drop-in — plays once on mount */
.cargo {
  animation: cargo-drop 0.55s cubic-bezier(0.25, 0.9, 0.35, 1) both;
}
@keyframes cargo-drop {
  0% {
    transform: translateY(-28px);
    opacity: 0;
  }
  60% {
    opacity: 1;
  }
  100% {
    transform: translateY(0);
    opacity: 1;
  }
}

/* gentle bob so the vessel feels like it is riding the water */
.ship-bob {
  animation: ship-bob 5s ease-in-out infinite;
}
@keyframes ship-bob {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}

.ship-scene__light {
  animation: mast-blink 2.4s ease-in-out infinite;
}
@keyframes mast-blink {
  0%,
  45%,
  100% {
    opacity: 0.25;
  }
  55%,
  90% {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cargo,
  .ship-bob,
  .ship-scene__light {
    animation: none;
  }
  .ship-scene__light {
    opacity: 0.7;
  }
}

/* Hide on narrow/mobile screens, AND whenever the viewport is taller than it
   is wide (portrait orientation) — the decorative 3D scene competes with
   content in that layout regardless of raw pixel width (e.g. a tablet held
   in portrait is well over 900px wide but still too cramped for this). */
@media (max-width: 900px), (orientation: portrait) {
  .ship-scene {
    display: none;
  }
}
</style>
