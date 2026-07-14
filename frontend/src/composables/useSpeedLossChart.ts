import { computed, type ComputedRef } from 'vue'
import type { NoonReportEntry, SpeedLossEvent } from '@/types/fleet'
import type { ChartThemeTokens } from '@/composables/useChartTheme'

function linearRegression(points: { x: number; y: number }[]) {
  const n = points.length
  if (n < 2) return { slope: 0, intercept: points[0]?.y ?? 0 }
  const sumX = points.reduce((s, p) => s + p.x, 0)
  const sumY = points.reduce((s, p) => s + p.y, 0)
  const sumXY = points.reduce((s, p) => s + p.x * p.y, 0)
  const sumXX = points.reduce((s, p) => s + p.x * p.x, 0)
  const denom = n * sumXX - sumX * sumX
  const slope = denom === 0 ? 0 : (n * sumXY - sumX * sumY) / denom
  const intercept = (sumY - slope * sumX) / n
  return { slope, intercept }
}

/**
 * Compact Speed Loss trend option for the chat overlay's mini card — same
 * color language and tooltip style as the full SpeedLoss page, but without
 * its interactive filters/regression-cycle-comparison state (that page's
 * chart is too entangled with page-local controls to share verbatim).
 */
export function useSpeedLossChart(
  reports: ComputedRef<NoonReportEntry[]>,
  events: ComputedRef<SpeedLossEvent[]>,
  chart: ComputedRef<ChartThemeTokens>,
) {
  return computed(() => {
    const c = chart.value
    const rows = reports.value
    const points = rows.map((r) => ({ x: r.day, y: r.speedLossPct }))
    const { slope, intercept } = linearRegression(points)
    const trendLine =
      points.length >= 2
        ? [
            [rows[0].day, intercept],
            [rows[rows.length - 1].day, slope * points[points.length - 1].x + intercept],
          ]
        : []

    return {
      animation: false,
      grid: { left: 36, right: 12, top: 12, bottom: 24 },
      tooltip: {
        trigger: 'item',
        backgroundColor: c.marineNavy,
        textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 11 },
        formatter: (p: any) => `Day ${p.value[0]}<br/>Speed Loss ${Number(p.value[1]).toFixed(1)}%`,
      },
      xAxis: {
        type: 'value',
        axisLabel: { show: false },
        axisLine: { lineStyle: { color: c.axisLine } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 9, color: c.inkSlate, formatter: '{value}%' },
        splitLine: { lineStyle: { color: c.splitLine } },
      },
      series: [
        {
          name: 'Speed Loss',
          type: 'scatter',
          symbolSize: 5,
          itemStyle: { color: c.brassAmber, opacity: 0.8 },
          data: rows.map((r) => [r.day, r.speedLossPct]),
        },
        {
          name: '污損趨勢擬合',
          type: 'line',
          showSymbol: false,
          lineStyle: { color: c.signalRed, width: 1.5, type: 'dashed' as const },
          data: trendLine,
        },
        {
          name: '事件標記',
          type: 'line',
          data: [],
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: c.fathomTeal, type: 'solid' as const, width: 1 },
            label: { show: false },
            data: events.value.map((e) => ({ xAxis: e.day })),
          },
        },
      ],
    }
  })
}
