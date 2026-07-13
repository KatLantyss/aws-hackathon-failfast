<script setup lang="ts">
// Horizontal Siri-style waveform — adapted from
// design_docs/voice/siri_style_waveform.html, recolored to the app's own
// teal / amber / CI-blue accents (the blue is the existing decorative hue
// used for the map hover glow, not a new color introduced just for this).
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{ analyser: AnalyserNode | null; active: boolean }>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let ctx: CanvasRenderingContext2D | null = null
let rafId: number | null = null
let phase = 0
const smooth = [0, 0, 0]

const LINE_COLORS = [
  [95, 196, 182], // fathom-teal-glow
  [217, 167, 92], // brass-amber-light
  [79, 163, 219], // brand-blue-light
]

function reduceMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function drawLine(width: number, height: number, color: number[], amp: number, freq: number, offset: number, alpha: number, lineW: number) {
  if (!ctx) return
  const cy = height / 2
  ctx.beginPath()
  for (let x = 0; x <= width; x += 4) {
    const t = x / width
    const envelope = Math.sin(Math.PI * t)
    const y = cy + Math.sin(t * Math.PI * freq + phase + offset) * amp * envelope
    if (x === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.strokeStyle = `rgba(${color.join(',')},${alpha})`
  ctx.lineWidth = lineW
  ctx.lineCap = 'round'
  ctx.stroke()
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  ctx.clearRect(0, 0, width, height)

  const analyser = props.active ? props.analyser : null
  const still = reduceMotion()

  if (!analyser) {
    if (!still) phase += 0.035
    drawLine(width, height, LINE_COLORS[0], 4, 3.2, 0, 0.6, 2.2)
    drawLine(width, height, LINE_COLORS[1], 3, 4.1, 1.4, 0.45, 1.8)
    drawLine(width, height, LINE_COLORS[2], 2, 2.4, 2.8, 0.4, 1.6)
  } else {
    const timeData = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(timeData)
    let sum = 0
    for (let i = 0; i < timeData.length; i++) {
      const v = (timeData[i] - 128) / 128
      sum += v * v
    }
    const rms = Math.sqrt(sum / timeData.length)
    // Sensitive target + fast attack so the swing from "quiet" to "talking"
    // reads as a dramatic amplitude jump, not just a slightly bigger line.
    const target = Math.min(rms * 6, 1)

    smooth[0] += (target - smooth[0]) * 0.35
    smooth[1] += (target * 0.85 - smooth[1]) * 0.22
    smooth[2] += (target * 0.7 - smooth[2]) * 0.15

    if (!still) phase += 0.045 + smooth[0] * 0.1

    drawLine(width, height, LINE_COLORS[0], 4 + smooth[0] * (height * 0.4), 3.0, 0, 0.95, 2.4)
    drawLine(width, height, LINE_COLORS[1], 3 + smooth[1] * (height * 0.32), 3.8, 1.4, 0.7, 2)
    drawLine(width, height, LINE_COLORS[2], 2 + smooth[2] * (height * 0.26), 2.4, 2.8, 0.55, 1.8)
  }

  if (!still) rafId = requestAnimationFrame(draw)
}

function resize() {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  const dpr = window.devicePixelRatio || 1
  canvas.width = canvas.clientWidth * dpr
  canvas.height = canvas.clientHeight * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

// keeps the static (reduced-motion) frame in sync when listening/speaking state changes
watch([() => props.active, () => props.analyser], () => {
  if (reduceMotion()) draw()
})

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d')
  resize()
  draw()
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  if (rafId !== null) cancelAnimationFrame(rafId)
})
</script>

<template>
  <!-- Deliberately no w-full/h-full here: the caller's classes (e.g. h-20)
       must win outright, not fight an equal-specificity class from this
       component for the same size utility. -->
  <canvas ref="canvasRef" class="block" aria-hidden="true" />
</template>
