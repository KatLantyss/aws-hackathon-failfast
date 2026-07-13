<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { VESSEL_REFS } from '@/mock/reference'

const canvasRef = ref<HTMLCanvasElement | null>(null)

let ctx: CanvasRenderingContext2D | null = null
let rafId: number | null = null
let angle = 0

function hashToUnit(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return (h % 1000) / 1000
}

/** Fixed pseudo-random positions per vessel (seeded by IMO) so the "fleet on sonar" motif reads as intentional, not noise. */
const blips = VESSEL_REFS.map((v) => ({
  angle: hashToUnit(v.imo) * Math.PI * 2,
  radius: 0.22 + hashToUnit(v.imo + 'r') * 0.68,
  phase: hashToUnit(v.imo + 'p') * Math.PI * 2,
}))

function resize() {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  const dpr = window.devicePixelRatio || 1
  canvas.width = canvas.clientWidth * dpr
  canvas.height = canvas.clientHeight * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function draw(animate: boolean) {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  const cx = width / 2
  const cy = height / 2
  const maxR = Math.min(width, height) * 0.46

  ctx.clearRect(0, 0, width, height)

  ctx.strokeStyle = 'rgba(95, 196, 182, 0.16)'
  ctx.lineWidth = 1
  for (let i = 1; i <= 4; i++) {
    ctx.beginPath()
    ctx.arc(cx, cy, (maxR * i) / 4, 0, Math.PI * 2)
    ctx.stroke()
  }
  ctx.beginPath()
  ctx.moveTo(cx - maxR, cy)
  ctx.lineTo(cx + maxR, cy)
  ctx.moveTo(cx, cy - maxR)
  ctx.lineTo(cx, cy + maxR)
  ctx.stroke()

  if (animate) {
    const sweepWidth = Math.PI / 5
    const steps = 28
    for (let i = 0; i < steps; i++) {
      const a = angle - (i / steps) * sweepWidth
      const alpha = (1 - i / steps) * 0.3
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.lineTo(cx + Math.cos(a) * maxR, cy + Math.sin(a) * maxR)
      ctx.strokeStyle = `rgba(95, 196, 182, ${alpha})`
      ctx.lineWidth = 2
      ctx.stroke()
    }
  }

  const t = performance.now() / 1000
  for (const b of blips) {
    const r = b.radius * maxR
    const x = cx + Math.cos(b.angle) * r
    const y = cy + Math.sin(b.angle) * r
    const pulse = animate ? 0.5 + 0.5 * Math.sin(t * 1.2 + b.phase) : 0.6
    ctx.beginPath()
    ctx.arc(x, y, 2 + pulse * 1.6, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(217, 167, 92, ${0.45 + pulse * 0.5})`
    ctx.fill()
  }

  if (animate) {
    angle += 0.012
    rafId = requestAnimationFrame(() => draw(true))
  }
}

function reduceMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function start() {
  const canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d')
  resize()
  draw(!reduceMotion())
}

onMounted(() => {
  start()
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  if (rafId !== null) cancelAnimationFrame(rafId)
})
</script>

<template>
  <canvas ref="canvasRef" class="absolute inset-0 w-full h-full pointer-events-none" aria-hidden="true" />
</template>
