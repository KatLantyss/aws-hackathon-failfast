import { computed } from 'vue'
import { useAppTheme } from './useAppTheme'

export interface ChartThemeTokens {
  inkSlate: string
  inkMuted: string
  marineNavy: string
  chartPaperHi: string
  brandRed: string
  brassAmber: string
  signalRed: string
  fathomTeal: string
  axisLine: string
  splitLine: string
}

/**
 * ECharts option objects are plain JS — they can't reference CSS custom
 * properties directly, so chart colors must be resolved to concrete hex
 * values and recomputed when the theme toggles. This composable centralizes
 * that resolution (reading the current --color-* values from :root/.dark)
 * so every chart view shares one theme-aware palette instead of each
 * hardcoding its own hex strings.
 *
 * Usage: `const chart = useChartTheme()` then reference `chart.value.inkSlate`
 * etc. inside a `computed()` chart option — the option will recompute
 * whenever isDark flips because this is itself a computed ref.
 */
export function useChartTheme() {
  const { isDark } = useAppTheme()

  return computed<ChartThemeTokens>(() => {
    // isDark is read here so this computed re-evaluates on theme toggle
    void isDark.value
    const root = getComputedStyle(document.documentElement)
    const v = (name: string, fallback: string) => root.getPropertyValue(name).trim() || fallback

    return {
      inkSlate: v('--color-ink-slate', '#26262a'),
      inkMuted: v('--color-ink-muted', '#5f5f66'),
      marineNavy: v('--color-marine-navy', '#181818'),
      chartPaperHi: v('--color-chart-paper-hi', '#faf9f7'),
      brandRed: v('--color-brand-red', '#d7191f'),
      brassAmber: v('--color-brass-amber', '#c08a3e'),
      signalRed: v('--color-signal-red', '#e2572b'),
      fathomTeal: v('--color-fathom-teal', '#3e7c74'),
      /** low-opacity axis line color, derived from inkSlate */
      axisLine: isDark.value ? 'rgba(230,230,235,0.28)' : 'rgba(40,49,60,0.35)',
      splitLine: isDark.value ? 'rgba(230,230,235,0.1)' : 'rgba(40,49,60,0.12)',
    }
  })
}
