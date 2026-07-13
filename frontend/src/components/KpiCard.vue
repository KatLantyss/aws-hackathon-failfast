<script setup lang="ts">
import { computed, toRef } from 'vue'
import PanelTag from './PanelTag.vue'
import { useCountUp } from '@/composables/useCountUp'

const props = defineProps<{
  code: string
  label: string
  /** Either a plain string (rendered as-is, no animation) or a number to
   * count up to via requestAnimationFrame. */
  value: string | number
  /** Formats the animated numeric value for display, e.g. formatUsd.
   * Ignored when `value` is a string. */
  formatter?: (n: number) => string
  sublabel?: string
  tone?: 'default' | 'amber' | 'teal' | 'red'
}>()

const toneColor: Record<string, string> = {
  default: 'var(--color-ink-slate)',
  amber: 'var(--color-brass-amber)',
  teal: 'var(--color-fathom-teal)',
  red: 'var(--color-signal-red)',
}

const accentClass: Record<string, string> = {
  default: 'panel--accent',
  amber: 'panel--accent',
  teal: 'panel--accent-teal',
  red: 'panel--accent-red',
}

// requestAnimationFrame count-up (adapted from bilashism's rAF counter,
// CodePen mZpZLx) — only meaningful for numeric KPIs; string values (e.g.
// pre-formatted labels) pass straight through unanimated.
const numericTarget = computed(() => (typeof props.value === 'number' ? props.value : 0))
const displayValue = useCountUp(toRef(numericTarget))

const renderedValue = computed(() => {
  if (typeof props.value === 'string') return props.value
  return props.formatter ? props.formatter(displayValue.value) : Math.round(displayValue.value).toLocaleString()
})
</script>

<template>
  <div class="panel px-4 pt-4 pb-4 flex flex-col gap-3" :class="accentClass[props.tone ?? 'default']">
    <div class="flex items-center justify-between">
      <PanelTag :code="code" class="w-fit" />
    </div>
    <p class="font-display text-[11px] tracking-[0.08em] text-[var(--color-ink-muted)] leading-tight">
      {{ label }}
    </p>
    <p
      class="font-data font-semibold text-[2.1rem] leading-[0.95] tabular-nums"
      :style="{ color: toneColor[tone ?? 'default'] }"
    >
      {{ renderedValue }}
    </p>
    <p v-if="sublabel" class="text-xs text-[var(--color-ink-muted)]">{{ sublabel }}</p>
  </div>
</template>
