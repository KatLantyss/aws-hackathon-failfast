<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary, NoonReportEntry } from '@/types/fleet'
import { fetchSpeedLoss } from '@/mock/api'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import { formatUsd } from '@/utils/format'
import { useChartTheme } from '@/composables/useChartTheme'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data, state } = useAsyncData(() => props.imo, fetchSpeedLoss)
const chart = useChartTheme()

// --- interactive controls ---------------------------------------------
const dateFrom = ref('')
const dateTo = ref('')
const maxBeaufort = ref(9)
const onlyCalmSeas = ref(false)
const showBallast = ref(true)
const showLaden = ref(true)
const compareLastCycle = ref(false)
const xAxisMode = ref<'date' | 'daysSinceClean'>('date')
const chartReady = ref(false)

watch(data, (v) => {
  if (v) {
    dateFrom.value = v.reports[0]?.date ?? ''
    dateTo.value = v.reports[v.reports.length - 1]?.date ?? ''
    chartReady.value = false
    requestAnimationFrame(() => requestAnimationFrame(() => (chartReady.value = true)))
  }
})

function daysBetween(a: string, b: string) {
  return Math.round((new Date(b + 'T00:00:00Z').getTime() - new Date(a + 'T00:00:00Z').getTime()) / 86400000)
}

const cleaningDates = computed(() => (data.value?.events.filter((e) => e.type === 'hull_cleaning').map((e) => e.date) ?? []).sort())

const currentCycleStart = computed(() => {
  const dates = cleaningDates.value.filter((d) => d <= (dateTo.value || '9999'))
  return dates.length ? dates[dates.length - 1] : data.value?.reports[0]?.date ?? ''
})

const previousCycleRange = computed(() => {
  const dates = cleaningDates.value
  const idx = dates.indexOf(currentCycleStart.value)
  if (idx <= 0) return null
  return { start: dates[idx - 1], end: dates[idx] }
})

function withinFilters(r: NoonReportEntry) {
  if (dateFrom.value && r.date < dateFrom.value) return false
  if (dateTo.value && r.date > dateTo.value) return false
  if (r.beaufort > maxBeaufort.value) return false
  if (onlyCalmSeas.value && r.beaufort > 3) return false
  if (r.loadCondition === 'ballast' && !showBallast.value) return false
  if (r.loadCondition === 'laden' && !showLaden.value) return false
  return true
}

const filteredReports = computed(() => (data.value ? data.value.reports.filter(withinFilters) : []))

function xValue(r: NoonReportEntry) {
  return xAxisMode.value === 'date' ? r.date : daysBetween(currentCycleStart.value, r.date)
}

const scatterBallast = computed(() =>
  filteredReports.value.filter((r) => r.loadCondition === 'ballast').map((r) => [xValue(r), r.speedLossPct, r]),
)
const scatterLaden = computed(() =>
  filteredReports.value.filter((r) => r.loadCondition === 'laden').map((r) => [xValue(r), r.speedLossPct, r]),
)

// simple linear regression for the fouling trend line, over currently visible points
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

const regressionForCurrentCycle = computed(() => {
  const points = filteredReports.value
    .filter((r) => r.date >= currentCycleStart.value)
    .map((r) => ({ x: daysBetween(currentCycleStart.value, r.date), y: r.speedLossPct }))
  return linearRegression(points)
})

const regressionLine = computed(() => {
  const { slope, intercept } = regressionForCurrentCycle.value
  const cyclePoints = filteredReports.value.filter((r) => r.date >= currentCycleStart.value)
  if (cyclePoints.length < 2) return []
  const days = cyclePoints.map((r) => daysBetween(currentCycleStart.value, r.date))
  const minD = Math.min(...days)
  const maxD = Math.max(...days)
  const toX = (d: number) => (xAxisMode.value === 'date' ? cyclePoints.find((r) => daysBetween(currentCycleStart.value, r.date) === d)?.date ?? d : d)
  return [
    [toX(minD), slope * minD + intercept],
    [toX(maxD), slope * maxD + intercept],
  ]
})

// previous cycle comparison series (aligned by days-since-clean regardless of xAxisMode)
const previousCycleSeries = computed(() => {
  if (!compareLastCycle.value || !previousCycleRange.value || !data.value) return []
  const { start, end } = previousCycleRange.value
  return data.value.reports
    .filter((r) => r.date >= start && r.date < end)
    .map((r) => [daysBetween(start, r.date), r.speedLossPct])
})

// --- side stats panel ---------------------------------------------------
const stats = computed(() => {
  const rows = filteredReports.value
  if (!rows.length || !data.value) return null
  const avgLoss = rows.reduce((s, r) => s + r.speedLossPct, 0) / rows.length
  const { slope } = regressionForCurrentCycle.value
  const growthPerMonth = slope * 30
  const fuelPricePerMt = 620
  const excessFuel = rows.reduce((s, r) => {
    const baseline = r.fuelConsumptionMt / (1 + Math.max(r.speedLossPct, 0) / 100 * 1.8)
    return s + Math.max(0, r.fuelConsumptionMt - baseline)
  }, 0)
  return {
    avgLoss,
    excessCostUsd: Math.round(excessFuel * fuelPricePerMt),
    growthPerMonth,
  }
})

const suggestedWindow = computed(() => props.vessel.nextRecommendedWindow)

// --- chart option ---------------------------------------------------
const chartOption = computed(() => {
  const isDateAxis = xAxisMode.value === 'date'
  const c = chart.value
  return {
    animation: false, // custom scan-sweep handled via chartReady reveal instead
    grid: { left: 56, right: 24, top: 48, bottom: 56 },
    legend: {
      top: 8,
      textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 12, color: c.inkSlate },
      data: ['Ballast', 'Laden', '污損趨勢擬合', '乾淨船體基準', ...(compareLastCycle.value ? ['上次清洗週期'] : [])],
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: c.marineNavy,
      borderWidth: 0,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (p: any) => {
        if (p.seriesName === 'Ballast' || p.seriesName === 'Laden') {
          const r: NoonReportEntry = p.data[2]
          return `<b>${r.date}</b><br/>Speed Loss ${r.speedLossPct.toFixed(1)}%<br/>海況 BF${r.beaufort} · ${
            r.loadCondition === 'laden' ? '滿載' : '壓載'
          }<br/>油耗 ${r.fuelConsumptionMt.toFixed(1)} MT/日${r.isAnomaly ? `<br/><span style="color:${c.signalRed}">⚠ ` + r.anomalyReason + '</span>' : ''}`
        }
        return `${p.seriesName}: ${Array.isArray(p.value) ? Number(p.value[1]).toFixed(2) : p.value}%`
      },
    },
    xAxis: {
      type: isDateAxis ? 'time' : 'value',
      name: isDateAxis ? '日期' : '距上次清洗天數',
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      name: 'Speed Loss %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: '{value}%' },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    dataZoom: [
      { type: 'slider', xAxisIndex: 0, bottom: 12, height: 18, borderColor: c.axisLine },
      { type: 'inside', xAxisIndex: 0 },
    ],
    series: [
      {
        name: 'Ballast',
        type: 'scatter',
        symbol: 'circle',
        symbolSize: 7,
        itemStyle: { color: c.brassAmber, opacity: 0.8 },
        data: scatterBallast.value,
      },
      {
        name: 'Laden',
        type: 'scatter',
        symbol: 'diamond',
        symbolSize: 8,
        itemStyle: { color: c.inkSlate, opacity: 0.8 },
        data: scatterLaden.value,
      },
      {
        name: '污損趨勢擬合',
        type: 'line',
        showSymbol: false,
        lineStyle: { color: c.signalRed, width: 2, type: 'dashed' },
        data: regressionLine.value,
        z: 5,
      },
      {
        name: '乾淨船體基準',
        type: 'line',
        showSymbol: false,
        lineStyle: { color: c.fathomTeal, width: 1.5 },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: c.fathomTeal, type: 'solid' },
          label: { formatter: '乾淨基準', fontFamily: 'IBM Plex Mono', fontSize: 10 },
          data: [{ yAxis: 0 }],
        },
        data: [],
      },
      ...(compareLastCycle.value
        ? [
            {
              name: '上次清洗週期',
              type: 'line' as const,
              showSymbol: false,
              lineStyle: { color: c.inkSlate, width: 1.5, type: 'dotted' as const },
              data: previousCycleSeries.value,
            },
          ]
        : []),
      {
        name: '事件標記',
        type: 'line',
        data: [],
        markLine: {
          silent: false,
          symbol: 'none',
          lineStyle: { color: c.brassAmber, type: 'solid', width: 1.2 },
          label: {
            formatter: (p: any) => data.value?.events.find((e) => e.date === p.value)?.label ?? '',
            fontFamily: 'IBM Plex Sans',
            fontSize: 10,
            rotate: 0,
          },
          data: isDateAxis ? (data.value?.events ?? []).map((e) => ({ xAxis: e.date })) : [],
        },
      },
    ],
  }
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- controls -->
    <p class="text-xs text-[var(--color-ink-slate)]/50 -mb-1">
      時間軸為本船資料起始後的相對天數換算而成（後端未提供實際日曆日期），僅供趨勢比較。Speed Loss % 為後端 {{ data?.cleanBaseline.source ?? 'FULL_SPD_STW_SLIP' }} 方法計算的實際數值。
    </p>
    <div class="panel p-3 flex flex-wrap items-center gap-4 text-sm">
      <PanelTag code="SPD-01" />
      <label class="flex items-center gap-2">
        <span class="text-xs text-[var(--color-ink-slate)]/60">橫軸</span>
        <select v-model="xAxisMode" class="border rounded-[2px] px-2 py-1 text-xs">
          <option value="date">時間</option>
          <option value="daysSinceClean">距上次清洗天數</option>
        </select>
      </label>
      <label class="flex items-center gap-2">
        <span class="text-xs text-[var(--color-ink-slate)]/60">起</span>
        <input v-model="dateFrom" type="date" class="border rounded-[2px] px-2 py-1 font-data text-xs" />
      </label>
      <label class="flex items-center gap-2">
        <span class="text-xs text-[var(--color-ink-slate)]/60">迄</span>
        <input v-model="dateTo" type="date" class="border rounded-[2px] px-2 py-1 font-data text-xs" />
      </label>
      <label class="flex items-center gap-2">
        <input v-model="onlyCalmSeas" type="checkbox" class="accent-[var(--color-brass-amber)]" />
        <span class="text-xs">僅顯示 Beaufort ≤ 3</span>
      </label>
      <label class="flex items-center gap-2">
        <input v-model="showBallast" type="checkbox" class="accent-[var(--color-brass-amber)]" />
        <span class="text-xs">Ballast</span>
      </label>
      <label class="flex items-center gap-2">
        <input v-model="showLaden" type="checkbox" class="accent-[var(--color-brass-amber)]" />
        <span class="text-xs">Laden</span>
      </label>
      <button
        class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide transition-colors"
        :class="
          compareLastCycle
            ? 'bg-[var(--color-brass-amber)] text-[var(--color-marine-navy)] border-[var(--color-brass-amber)]'
            : 'hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)]'
        "
        :disabled="!previousCycleRange"
        @click="compareLastCycle = !compareLastCycle"
      >
        比較上次清洗週期
      </button>
    </div>

    <StateDisplay
      v-if="state !== 'success'"
      :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
      empty-title="此船尚無 Speed Loss 資料"
    />
    <div v-else class="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4">
      <div class="panel p-3">
        <div class="h-[440px]" :class="chartReady ? 'animate-scan' : 'opacity-0'">
          <VChart :option="chartOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <div class="flex flex-col gap-3">
        <div class="panel p-4" v-if="stats">
          <PanelTag code="STAT-01" class="mb-2" />
          <dl class="flex flex-col gap-3 text-sm">
            <div>
              <dt class="text-xs text-[var(--color-ink-slate)]/60">平均 Speed Loss</dt>
              <dd class="font-data text-xl">{{ stats.avgLoss.toFixed(2) }}%</dd>
            </div>
            <div>
              <dt class="text-xs text-[var(--color-ink-slate)]/60">估算超額油耗成本（區間內）</dt>
              <dd class="font-data text-xl text-[var(--color-signal-red)]">{{ formatUsd(stats.excessCostUsd) }}</dd>
            </div>
            <div>
              <dt class="text-xs text-[var(--color-ink-slate)]/60">污損增長速率</dt>
              <dd class="font-data text-xl">{{ stats.growthPerMonth.toFixed(2) }}%/月</dd>
            </div>
          </dl>
        </div>

        <div class="panel p-4 border-l-4" style="border-left-color: var(--color-brass-amber)">
          <PanelTag code="REC-01" class="mb-2" />
          <p class="font-display text-sm mb-1">建議下次清洗窗口</p>
          <p class="font-data text-base text-[var(--color-brass-amber)]">
            {{ suggestedWindow.start }} — {{ suggestedWindow.end }}
          </p>
          <p class="text-xs text-[var(--color-ink-slate)]/70 mt-2">
            污損增長速率{{ stats && stats.growthPerMonth > 0.5 ? '高於' : '接近' }}船隊平均，建議依此區間安排下次船體清洗。
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
