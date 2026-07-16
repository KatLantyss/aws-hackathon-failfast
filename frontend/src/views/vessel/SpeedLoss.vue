<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary, NoonReportEntry } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import { fetchSpeedLossData } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { formatUsd, formatDay } from '@/utils/format'
import { useChartTheme } from '@/composables/useChartTheme'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data, state } = useAsyncData(() => props.imo, fetchSpeedLossData)
const chart = useChartTheme()

const dsChart: DataSourceInfo = {
  status: 'hybrid',
  endpoint: ['GET /api/v1/vessels/{vessel_id}/speed-loss', 'GET /api/v1/vessels/{vessel_id}/maintenance-events'],
  description: '散布點與事件標記是後端原始資料；污損趨勢擬合線是前端現場算的線性回歸，後端沒有提供斜率欄位。',
  fields: [
    { ui: 'Ballast / Laden 散布點', source: 'iso_timeline[].stw / ref_stw（slip_timeline 為 fallback）' },
    { ui: '事件標記線', source: 'maintenance-events[].event_day / event_type' },
    { ui: '污損趨勢擬合線（紅色虛線）', source: '前端 linearRegression()', note: '純前端計算，非後端欄位' },
    { ui: '乾淨船體基準線', source: '固定 y=0 markLine，僅示意，無對應資料' },
  ],
}

const dsStats: DataSourceInfo = {
  status: 'hybrid',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/speed-loss + fleet/summary',
  description: '篩選區間平均與污損增長速率是前端對目前篩選後的資料點現場計算；近90天平均/最新數值與超額成本則是 fleet/summary 的後端原始欄位。',
  fields: [
    { ui: '篩選區間平均 Speed Loss', source: '前端對 filteredReports 取平均', note: '來源資料點是 real，但平均值本身是前端算的' },
    { ui: '近90天平均 / 最新', source: 'vessel.avgSpeedLossPct / vessel.speedLossPct（fleet/summary）' },
    { ui: '超額燃油成本（USD/天）', source: 'vessel.excessFuelCostUsdMtd × 篩選筆數', note: '前端相乘，非後端提供的「區間成本」' },
    { ui: '污損增長速率（%/月）', source: '前端回歸 slope × 30', note: '純前端計算' },
  ],
}

const dsRec: DataSourceInfo = {
  status: 'hybrid',
  endpoint: 'GET /api/v1/fleet/summary',
  description: '「建議下次清洗窗口」= day_range_max + 30 ~ +60，是前端固定加 30/60 天推算，不是後端 maintenance-recommendation 端點的建議值（那支端點只在維修效能分析頁被使用）。',
  fields: [
    { ui: '建議下次清洗窗口', source: 'vessel.nextRecommendedWindow = day_range_max + 30 / +60', note: '前端固定天數推算' },
  ],
}

// --- interactive controls ---------------------------------------------
// dayFrom/dayTo filter on the raw day-index (the dataset has no calendar date).
const dayFrom = ref<number | null>(null)
const dayTo = ref<number | null>(null)
const maxBeaufort = ref(9)
const onlyCalmSeas = ref(false)
const compareLastCycle = ref(false)
const xAxisMode = ref<'day' | 'daysSinceClean'>('day')
const chartReady = ref(false)

watch(data, (v) => {
  if (v) {
    dayFrom.value = v.reports[0]?.day ?? null
    dayTo.value = v.reports[v.reports.length - 1]?.day ?? null
    chartReady.value = false
    requestAnimationFrame(() => requestAnimationFrame(() => (chartReady.value = true)))
  }
})

// Drydock resets the hull too (backend's HULL_CLEAN_TYPES includes DD), and
// 'inspection' (pure UWI) must never count as a cycle boundary — it performs
// no physical work, per the dataset's "inspection-only events don't restore
// performance" rule.
const cleaningDays = computed(() =>
  (data.value?.events.filter((e) => e.type === 'hull_cleaning' || e.type === 'drydock').map((e) => e.day) ?? []).sort((a, b) => a - b),
)

const currentCycleStart = computed(() => {
  const days = cleaningDays.value.filter((d) => d <= (dayTo.value ?? Infinity))
  return days.length ? days[days.length - 1] : data.value?.reports[0]?.day ?? 0
})

const previousCycleRange = computed(() => {
  const days = cleaningDays.value
  const idx = days.indexOf(currentCycleStart.value)
  if (idx <= 0) return null
  return { start: days[idx - 1], end: days[idx] }
})

function withinFilters(r: NoonReportEntry) {
  if (dayFrom.value != null && r.day < dayFrom.value) return false
  if (dayTo.value != null && r.day > dayTo.value) return false
  if (r.beaufort > maxBeaufort.value) return false
  if (onlyCalmSeas.value && r.beaufort > 3) return false
  return true
}

const filteredReports = computed(() => (data.value ? data.value.reports.filter(withinFilters) : []))

function xValue(r: NoonReportEntry) {
  return xAxisMode.value === 'day' ? r.day : r.day - currentCycleStart.value
}

const scatterData = computed(() =>
  filteredReports.value
    .filter((r) => r.speedLossPct != null)
    .map((r) => [xValue(r), r.speedLossPct, r]),
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
    .filter((r) => r.day >= currentCycleStart.value)
    .map((r) => ({ x: r.day - currentCycleStart.value, y: r.speedLossPct }))
  return linearRegression(points)
})

const regressionLine = computed(() => {
  const { slope, intercept } = regressionForCurrentCycle.value
  const cyclePoints = filteredReports.value.filter((r) => r.day >= currentCycleStart.value)
  if (cyclePoints.length < 2) return []
  const days = cyclePoints.map((r) => r.day - currentCycleStart.value)
  const minD = Math.min(...days)
  const maxD = Math.max(...days)
  const toX = (d: number) => (xAxisMode.value === 'day' ? d + currentCycleStart.value : d)
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
    .filter((r) => r.day >= start && r.day < end)
    .map((r) => [r.day - start, r.speedLossPct])
})

// --- side stats panel ---------------------------------------------------
const stats = computed(() => {
  const rows = filteredReports.value
  if (!rows.length || !data.value) return null
  const avgLoss = rows.reduce((s, r) => s + r.speedLossPct, 0) / rows.length
  const { slope } = regressionForCurrentCycle.value
  const growthPerMonth = slope * 30
  // Use pre-computed excess cost from fleet-summary DynamoDB (already USD/day)
  const excessCostUsd = Math.round((props.vessel.excessFuelCostUsdMtd ?? 0) * rows.length)
  return {
    avgLoss,
    excessCostUsd,
    growthPerMonth,
  }
})

const suggestedWindow = computed(() => props.vessel.nextRecommendedWindow)

// --- chart option ---------------------------------------------------
const chartOption = computed(() => {
  const isDayAxis = xAxisMode.value === 'day'
  const c = chart.value
  return {
    animation: false, // custom scan-sweep handled via chartReady reveal instead
    grid: { left: 56, right: 24, top: 48, bottom: 56 },
    legend: {
      top: 8,
      textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 12, color: c.inkSlate },
      data: ['Speed Loss', '污損趨勢擬合', '乾淨船體基準', ...(compareLastCycle.value ? ['上次清洗週期'] : [])],
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: c.marineNavy,
      borderWidth: 0,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (p: any) => {
        if (p.seriesName === 'Speed Loss') {
          const r: NoonReportEntry = p.data[2]
          return `<b>Day ${r.day}</b><br/>Speed Loss ${r.speedLossPct.toFixed(1)}%<br/>海況 BF${r.beaufort}`
        }
        return `${p.seriesName}: ${Array.isArray(p.value) ? Number(p.value[1]).toFixed(2) : p.value}%`
      },
    },
    xAxis: {
      type: 'value',
      name: isDayAxis ? 'Day' : '距上次清洗天數',
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
      scale: false,
      min: (value: any) => {
        // 動態計算最小值，確保包含負值（outperformance cases）
        if (value.min < -5) return Math.floor(value.min * 1.1)  // 負值情況
        return value.min < 0 ? -5 : -Math.abs(value.max) * 0.5  // 確保負值區域可見
      },
      max: (value: any) => {
        // 動態計算最大值
        return Math.ceil(value.max * 1.1)
      },
      axisLine: {
        lineStyle: { color: c.axisLine },
        onZero: false,  // 改為 false，讓 0 基準線在下方而不是中間
      },
    },
    dataZoom: [
      { type: 'slider', xAxisIndex: 0, bottom: 12, height: 18, borderColor: c.axisLine },
      { type: 'inside', xAxisIndex: 0 },
    ],
    series: [
      {
        name: 'Speed Loss',
        type: 'scatter',
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: c.brassAmber, opacity: 0.8 },
        data: scatterData.value,
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
            formatter: (p: any) => data.value?.events.find((e) => e.day === p.value)?.label ?? '',
            fontFamily: 'IBM Plex Sans',
            fontSize: 10,
            rotate: 0,
          },
          data: isDayAxis ? (data.value?.events ?? []).map((e) => ({ xAxis: e.day })) : [],
        },
      },
    ],
  }
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- controls -->
    <div class="panel p-3 flex flex-wrap items-center gap-4 text-sm">
      <label class="flex items-center gap-2">
        <span class="text-xs text-[var(--color-ink-slate)]/60">橫軸</span>
        <select v-model="xAxisMode" class="border rounded-[2px] px-2 py-1 text-xs">
          <option value="day">Day 序號</option>
          <option value="daysSinceClean">距上次清洗天數</option>
        </select>
      </label>
      <label class="flex items-center gap-2">
        <span class="text-xs text-[var(--color-ink-slate)]/60">起 (Day)</span>
        <input v-model.number="dayFrom" type="number" class="border rounded-[2px] px-2 py-1 font-data text-xs w-20" />
      </label>
      <label class="flex items-center gap-2">
        <span class="text-xs text-[var(--color-ink-slate)]/60">迄 (Day)</span>
        <input v-model.number="dayTo" type="number" class="border rounded-[2px] px-2 py-1 font-data text-xs w-20" />
      </label>
      <label class="flex items-center gap-2">
        <input v-model="onlyCalmSeas" type="checkbox" class="accent-[var(--color-brass-amber)]" />
        <span class="text-xs">僅顯示 Beaufort ≤ 3</span>
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
        <DataSourceTag :info="dsChart" />
        <div class="h-[440px]" :class="chartReady ? 'animate-scan' : 'opacity-0'">
          <VChart :option="chartOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <div class="flex flex-col gap-3">
        <div class="panel p-4" v-if="stats">
          <DataSourceTag :info="dsStats" />
          <dl class="flex flex-col gap-3 text-sm">
            <div>
              <dt class="text-xs text-[var(--color-ink-slate)]/60">篩選區間平均 Speed Loss</dt>
              <dd class="font-data text-xl">{{ stats.avgLoss.toFixed(2) }}%</dd>
            </div>
            <div>
              <dt class="text-xs text-[var(--color-ink-slate)]/60">近90天平均</dt>
              <dd class="font-data text-base">
                {{ vessel.avgSpeedLossPct != null ? vessel.avgSpeedLossPct.toFixed(2) + '%' : '—' }}
                <span class="text-xs text-[var(--color-ink-slate)]/50 ml-1">/ 最新 {{ vessel.speedLossPct.toFixed(2) }}%</span>
              </dd>
            </div>
            <div>
              <dt class="text-xs text-[var(--color-ink-slate)]/60">超額燃油成本（USD/天）</dt>
              <dd class="font-data text-xl text-[var(--color-signal-red)]">{{ formatUsd(vessel.excessFuelCostUsdMtd) }}</dd>
            </div>
            <div>
              <dt class="text-xs text-[var(--color-ink-slate)]/60">污損增長速率（回歸）</dt>
              <dd class="font-data text-xl">{{ stats.growthPerMonth.toFixed(2) }}%/月</dd>
            </div>
            <div v-if="vessel.avgConsumptionMt">
              <dt class="text-xs text-[var(--color-ink-slate)]/60">平均主機油耗</dt>
              <dd class="font-data text-base">{{ vessel.avgConsumptionMt.toFixed(1) }} MT/天</dd>
            </div>
            <div>
              <dt class="text-xs text-[var(--color-ink-slate)]/60">距上次水下清洗</dt>
              <dd class="font-data text-base"
                :class="vessel.daysSinceHullClean > 730 ? 'text-[var(--color-signal-red)]' : vessel.daysSinceHullClean > 365 ? 'text-[var(--color-brass-amber)]' : ''"
              >{{ vessel.daysSinceHullClean }} 天</dd>
            </div>
          </dl>
        </div>

      </div>
    </div>
  </div>
</template>
