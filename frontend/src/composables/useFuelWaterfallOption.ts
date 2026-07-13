import { computed, type ComputedRef, type Ref } from 'vue'
import type { FuelAttributionFactor, FuelAttributionResponse } from '@/types/fleet'
import type { ChartThemeTokens } from '@/composables/useChartTheme'

const WEATHER_COLOR = '#8FA6B2'

export function fuelFactorColors(chart: ChartThemeTokens): Record<FuelAttributionFactor['factor'], string> {
  return {
    weather: WEATHER_COLOR,
    hull_fouling: chart.signalRed,
    propeller_fouling: chart.brassAmber,
    engine_degradation: chart.inkSlate,
  }
}

/** Baseline -> +weather -> +hull -> +propeller -> +engine -> actual waterfall option. Shared by the full Fuel Attribution page and the chat overlay's compact card. */
export function useFuelWaterfallOption(
  data: Ref<FuelAttributionResponse | null | undefined> | ComputedRef<FuelAttributionResponse | null | undefined>,
  chart: ComputedRef<ChartThemeTokens>,
  options: { compact?: boolean } = {},
) {
  return computed(() => {
    if (!data.value) return {}
    const c = chart.value
    const factorColors = fuelFactorColors(c)
    const { baselineFuelMt, attribution, actualFuelMt } = data.value
    const labels = ['基準油耗', ...attribution.map((a) => a.label), '實際油耗']
    let running = baselineFuelMt
    const helperBase = [0]
    const values: number[] = [baselineFuelMt]
    for (const a of attribution) {
      helperBase.push(running)
      values.push(a.impactMt)
      running += a.impactMt
    }
    helperBase.push(0)
    values.push(actualFuelMt)

    const barColors = [c.inkSlate, ...attribution.map((a) => factorColors[a.factor]), c.fathomTeal]
    const compact = options.compact ?? false

    return {
      animation: false,
      grid: compact ? { left: 40, right: 12, top: 16, bottom: 32 } : { left: 56, right: 24, top: 24, bottom: 48 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: c.marineNavy,
        textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
        formatter: (params: any[]) => {
          const idx = params[0].dataIndex
          const label = labels[idx]
          const val = values[idx]
          if (idx === 0) return `${label}: ${val.toFixed(2)} MT`
          if (idx === labels.length - 1) return `${label}: ${val.toFixed(2)} MT`
          const pctOfExcess = (((val / (actualFuelMt - baselineFuelMt)) * 100) || 0).toFixed(0)
          return `${label}<br/>多燒 ${val.toFixed(2)} 噸燃油，約占超額油耗的 ${pctOfExcess}%`
        },
      },
      xAxis: {
        type: 'category',
        data: labels,
        axisLabel: { fontFamily: 'IBM Plex Sans', fontSize: compact ? 9 : 11, color: c.inkSlate, interval: 0, rotate: compact ? 30 : 0 },
        axisLine: { lineStyle: { color: c.axisLine } },
      },
      yAxis: {
        type: 'value',
        name: compact ? undefined : 'MT/日',
        nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
        axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
        splitLine: { lineStyle: { color: c.splitLine } },
      },
      series: [
        { name: 'base', type: 'bar', stack: 'total', silent: true, itemStyle: { color: 'transparent' }, data: helperBase },
        {
          name: 'value',
          type: 'bar',
          stack: 'total',
          barWidth: '55%',
          data: values.map((v, i) => ({ value: v, itemStyle: { color: barColors[i] } })),
          label: compact
            ? undefined
            : { show: true, position: 'top', formatter: (p: any) => p.value.toFixed(1), fontFamily: 'IBM Plex Mono', fontSize: 11 },
        },
      ],
    }
  })
}
