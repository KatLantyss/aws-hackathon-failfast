import { onBeforeUnmount, ref, watch, type Ref } from 'vue'

/**
 * requestAnimationFrame-based "count up" number animation — adapted from
 * bilashism's rAF counter (CodePen mZpZLx): linear interpolation from the
 * previously displayed value to the new target, driven frame-by-frame via
 * requestAnimationFrame rather than a CSS transition (which can't animate
 * discrete text content like a KPI number).
 *
 * Re-animates from the CURRENT displayed value (not always from 0) whenever
 * `target` changes, so live data refreshes visibly tick up/down instead of
 * just snapping. On first mount the initial displayed value is 0, so KPI
 * cards count up from 0 the first time they render.
 */
export function useCountUp(target: Ref<number>, duration = 900) {
  const displayValue = ref(0)
  let rafId: number | null = null

  function animateTo(to: number) {
    if (rafId !== null) cancelAnimationFrame(rafId)

    const prefersReducedMotion =
      typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReducedMotion) {
      displayValue.value = to
      return
    }

    const from = displayValue.value
    const diff = to - from
    if (diff === 0) return

    let start: number | null = null
    const step = (timestamp: number) => {
      if (start === null) start = timestamp
      const progress = Math.min((timestamp - start) / duration, 1)
      displayValue.value = from + diff * progress
      if (progress < 1) {
        rafId = requestAnimationFrame(step)
      } else {
        displayValue.value = to
        rafId = null
      }
    }
    rafId = requestAnimationFrame(step)
  }

  watch(target, (newVal) => animateTo(newVal), { immediate: true })

  onBeforeUnmount(() => {
    if (rafId !== null) cancelAnimationFrame(rafId)
  })

  return displayValue
}
