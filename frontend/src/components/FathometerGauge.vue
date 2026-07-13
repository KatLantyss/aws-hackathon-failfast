<script setup lang="ts">
// Signature element per design_docs section 3.5:
// a vertical "fathometer" style scale where a needle position represents a
// single risk metric (fouling / speed loss / days-to-maintenance), with
// Clean/Light/Moderate/Heavy color bands.
import { computed } from 'vue'
import type { FoulingGrade } from '@/types/fleet'

const props = defineProps<{
  /** current value 0-100 (already normalized) */
  value: number
  grade: FoulingGrade
  label?: string
  unit?: string
  /** raw display value, e.g. "6.4%" — falls back to value+unit */
  displayValue?: string
  size?: 'sm' | 'md' | 'lg'
}>()

const bands: { grade: FoulingGrade; from: number; to: number; color: string }[] = [
  { grade: 'Clean', from: 0, to: 25, color: 'var(--color-fathom-teal)' },
  { grade: 'Light', from: 25, to: 50, color: 'var(--color-fouling-light)' },
  { grade: 'Moderate', from: 50, to: 80, color: 'var(--color-brass-amber)' },
  { grade: 'Heavy', from: 80, to: 100, color: 'var(--color-signal-red)' },
]

const clamped = computed(() => Math.max(0, Math.min(100, props.value)))
const needleTopPct = computed(() => 100 - clamped.value)

const gradeColor = computed(() => bands.find((b) => b.grade === props.grade)?.color ?? 'var(--color-ink-slate)')

const dims = computed(() => {
  switch (props.size) {
    case 'sm':
      return { height: 96, width: 22 }
    case 'lg':
      return { height: 220, width: 36 }
    default:
      return { height: 140, width: 28 }
  }
})
</script>

<template>
  <div class="flex items-start gap-3" role="img" :aria-label="`${label ?? '風險量表'}: ${grade}, ${displayValue ?? value + (unit ?? '')}`">
    <div class="relative shrink-0" :style="{ height: dims.height + 'px', width: dims.width + 'px' }">
      <!-- scale tube -->
      <div
        class="absolute inset-0 rounded-[2px] overflow-hidden border"
        style="border-color: color-mix(in srgb, var(--color-ink-slate) 35%, transparent)"
      >
        <div
          v-for="band in bands"
          :key="band.grade"
          class="absolute left-0 right-0"
          :style="{
            top: 100 - band.to + '%',
            height: band.to - band.from + '%',
            background: band.color,
            opacity: 0.85,
          }"
        />
        <!-- tick marks -->
        <div
          v-for="tick in [0, 25, 50, 75, 100]"
          :key="tick"
          class="absolute left-0 right-0 h-px"
          style="background: rgba(255,255,255,0.55)"
          :style="{ top: 100 - tick + '%' }"
        />
      </div>
      <!-- needle -->
      <div
        class="absolute left-[-4px] right-[-4px] flex items-center transition-[top] duration-500 ease-out"
        :style="{ top: `calc(${needleTopPct}% - 1px)` }"
      >
        <div class="h-[3px] flex-1 bg-[var(--color-ink-slate)]" />
        <div
          class="h-2 w-2 rounded-full border border-[var(--color-ink-slate)] shrink-0"
          style="background: var(--color-chart-paper-hi)"
        />
      </div>
    </div>
    <div class="flex flex-col justify-between font-data text-xs" :style="{ height: dims.height + 'px' }">
      <div>
        <p v-if="label" class="uppercase tracking-wide text-[10px] text-[var(--color-ink-slate)]/60 font-body mb-0.5">
          {{ label }}
        </p>
        <p class="text-lg font-semibold leading-none" :style="{ color: gradeColor }">
          {{ displayValue ?? `${value}${unit ?? ''}` }}
        </p>
      </div>
      <span
        class="inline-flex items-center gap-1.5 uppercase text-[10px] tracking-wide font-body font-semibold px-1.5 py-0.5 rounded-[2px] border w-fit"
        :style="{ color: gradeColor, borderColor: gradeColor }"
      >
        <span class="status-dot" :style="{ background: gradeColor }" />
        {{ grade }}
      </span>
    </div>
  </div>
</template>
