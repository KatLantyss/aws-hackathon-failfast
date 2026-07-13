<script setup lang="ts">
// Ambient ocean — perspective point-grid waves driven by value noise.
//
// The referenced demo (codesandbox "waves by value noise") gets its 3D read
// from a real camera: a grid of points laid flat on the ground, viewed at a
// raking angle, with each point's height displaced by noise. Near points are
// big/bright/widely spaced; far points shrink and crowd together toward a
// horizon. A flat top-down projection (our previous version) has none of
// that — hence it read as 2D no matter how the lines wiggled.
//
// This version reproduces the same effect on a 2D canvas by doing the
// perspective projection by hand: rows go from a horizon line (far, small,
// dim, tightly packed) down to the foreground (near, large, bright, widely
// spread), and each point's noise-driven height is scaled by the same
// per-row depth factor — exactly like a displaced 3D plane would foreshorten
// under a camera. Sits at Layer 0, ship floats above it, content on top.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { useAppTheme } from '@/composables/useAppTheme'

// Canvas can't read CSS custom properties, so the sea palette is duplicated
// here as JS constants and swapped explicitly when the theme toggles.
const { isDark } = useAppTheme()

// Same threshold as BrandShipScene: hide the decorative ocean on narrow
// screens AND in portrait orientation (e.g. a tablet held upright is wide
// enough by pixel count but still too cramped for this ambient effect).
// The animation loop itself is paused while hidden, not just the canvas
// visually hidden, to avoid burning CPU/battery for an invisible effect.
const isCompact = useMediaQuery('(max-width: 900px), (orientation: portrait)')

const canvasRef = ref<HTMLCanvasElement | null>(null)
let ctx: CanvasRenderingContext2D | null = null
let raf = 0
let width = 0
let height = 0
let dpr = 1
let onResize: (() => void) | null = null

// ---- value noise (fbm) -----------------------------------------------
function hash(x: number, y: number): number {
  const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453
  return n - Math.floor(n)
}
function smooth(t: number): number {
  return t * t * (3 - 2 * t)
}
function valueNoise(x: number, y: number): number {
  const xi = Math.floor(x)
  const yi = Math.floor(y)
  const xf = x - xi
  const yf = y - yi
  const v00 = hash(xi, yi)
  const v10 = hash(xi + 1, yi)
  const v01 = hash(xi, yi + 1)
  const v11 = hash(xi + 1, yi + 1)
  const u = smooth(xf)
  const v = smooth(yf)
  return (v00 * (1 - u) + v10 * u) * (1 - v) + (v01 * (1 - u) + v11 * u) * v
}
function fbm(x: number, y: number): number {
  let f = 0
  let amp = 0.5
  let freq = 1
  for (let i = 0; i < 3; i++) {
    f += amp * valueNoise(x * freq, y * freq)
    freq *= 2
    amp *= 0.5
  }
  return f
}

// ---- perspective point-grid -------------------------------------------
const ROWS = 42 // depth samples, far (0) → near (ROWS-1)
const COLS = 84 // across samples per row
const HORIZON_FRAC = 0.42 // horizon sits ~42% down the viewport
const DEPTH_POW = 2.1 // >1 packs far rows tightly near the horizon
const SPREAD_POW = 1.5 // grid width growth curve toward the foreground

// Frequency/amplitude/speed tuned toward the reference sliders
// (Frequency ≈3, Amplitude ≈0.2 of point spacing, Speed ≈0.41).
const FREQ_X = 2.6
const FREQ_Z = 2.2
const AMPLITUDE = 30 // world height scale (px) at full near-scale
const SPEED = 0.42

// Deep muted teal-slate sea + dimmed foam — matches the brand's light/red/
// cream palette instead of a generic light blue. Dark-mode variant is
// brightened slightly so the waves stay visible against the darker page.
const SEA_DEEP_LIGHT: [number, number, number] = [24, 46, 45]
const SEA_FOAM_LIGHT: [number, number, number] = [120, 172, 163]
const SEA_DEEP_DARK: [number, number, number] = [18, 38, 40]
const SEA_FOAM_DARK: [number, number, number] = [95, 196, 182]

let SEA_DEEP: [number, number, number] = SEA_DEEP_LIGHT
let SEA_FOAM: [number, number, number] = SEA_FOAM_LIGHT

function mix(a: [number, number, number], b: [number, number, number], t: number): string {
  const r = Math.round(a[0] + (b[0] - a[0]) * t)
  const g = Math.round(a[1] + (b[1] - a[1]) * t)
  const bl = Math.round(a[2] + (b[2] - a[2]) * t)
  return `${r},${g},${bl}`
}

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  width = window.innerWidth
  height = window.innerHeight
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = width * dpr
  canvas.height = height * dpr
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`
  ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function drawFrame(t: number) {
  if (!ctx) return
  ctx.clearRect(0, 0, width, height)

  const horizonY = height * HORIZON_FRAC
  const vanishX = width * 0.52
  const halfSpread = width * 0.68

  // far rows drawn first so near rows correctly overlap them
  for (let j = 0; j < ROWS; j++) {
    const zt = j / (ROWS - 1) // 0 far → 1 near
    const depthEase = Math.pow(zt, DEPTH_POW)
    const spreadEase = Math.pow(zt, SPREAD_POW)
    const baseY = horizonY + (height - horizonY) * depthEase
    const rowScale = 0.035 + 0.965 * spreadEase // shared depth factor: size/spread/height/alpha
    const rowAlpha = 0.06 + 0.62 * spreadEase

    for (let i = 0; i < COLS; i++) {
      const xt = (i / (COLS - 1)) * 2 - 1 // -1..1
      const screenX = vanishX + xt * halfSpread * rowScale

      const n = fbm(xt * FREQ_X + t * SPEED * 0.5, zt * FREQ_Z - t * SPEED)
      const hNorm = n - 0.5 // -0.5..0.5, trough..crest
      const heightPx = hNorm * AMPLITUDE * rowScale
      const screenY = baseY - heightPx

      const crestT = hNorm + 0.5 // 0 trough → 1 crest
      const radius = (0.5 + 2.1 * rowScale) * (0.75 + 0.5 * crestT)
      const alpha = rowAlpha * (0.45 + 0.65 * crestT)

      ctx.beginPath()
      ctx.arc(screenX, screenY, radius, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${mix(SEA_DEEP, SEA_FOAM, crestT)},${alpha.toFixed(3)})`
      ctx.fill()
    }
  }
}

function loop() {
  drawFrame(performance.now() * 0.001)
  raf = requestAnimationFrame(loop)
}

function stopLoop() {
  if (raf) cancelAnimationFrame(raf)
  raf = 0
}

function startLoop() {
  if (raf || isCompact.value) return
  if (reduceMotion) {
    drawFrame(0)
    return
  }
  raf = requestAnimationFrame(loop)
}

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

watch(
  isDark,
  (dark) => {
    SEA_DEEP = dark ? SEA_DEEP_DARK : SEA_DEEP_LIGHT
    SEA_FOAM = dark ? SEA_FOAM_DARK : SEA_FOAM_LIGHT
    if (reduceMotion || isCompact.value) drawFrame(0) // repaint the static frame immediately
  },
  { immediate: true },
)

// pause/resume the animation loop (and clear the canvas while hidden) when
// crossing the compact-layout threshold, instead of just hiding it visually
watch(isCompact, (compact) => {
  if (compact) {
    stopLoop()
    ctx?.clearRect(0, 0, width, height)
  } else {
    startLoop()
  }
})

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d')
  resize()
  startLoop()
  onResize = () => resize()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  stopLoop()
  if (onResize) window.removeEventListener('resize', onResize)
})
</script>

<template>
  <canvas v-show="!isCompact" ref="canvasRef" class="wave-field" aria-hidden="true" />
</template>

<style scoped>
.wave-field {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}
</style>
