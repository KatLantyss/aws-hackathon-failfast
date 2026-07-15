<script setup lang="ts">
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import { getSpeedLossDashboard } from '@/services/backend'
import { fetchCorrelation } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import { useChartTheme } from '@/composables/useChartTheme'
import StateDisplay from '@/components/StateDisplay.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { formatDay, formatUsd, formatNumber, formatPct } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data: slData, state: slState } = useAsyncData(() => props.imo, getSpeedLossDashboard)
const { data: maintData, state: maintState } = useAsyncData(() => props.imo, fetchCorrelation)
const chart = useChartTheme()

// Tab 切換
const activeTab = ref<'attribution' | 'maintenance'>('attribution')

// 維修成本編輯
const costEditorOpen = ref(false)
const selectedEventId = ref('')
const maintenanceCostInput = ref('')
const maintenanceCosts = ref<Record<string, number>>({})

const storageKey = `maintenance-costs-${props.imo}`
const loadCosts = () => {
  try {
    const stored = localStorage.getItem(storageKey)
    if (stored) maintenanceCosts.value = JSON.parse(stored)
  } catch (e) {
    console.error('Failed to load maintenance costs:', e)
  }
}

const saveCosts = () => {
  try {
    localStorage.setItem(storageKey, JSON.stringify(maintenanceCosts.value))
  } catch (e) {
    console.error('Failed to save maintenance costs:', e)
  }
}

const openCostEditor = (eventId: string, currentCost: number) => {
  selectedEventId.value = eventId
  maintenanceCostInput.value = currentCost.toString()
  costEditorOpen.value = true
}

const saveCostForEvent = () => {
  const cost = parseInt(maintenanceCostInput.value) || 0
  if (selectedEventId.value && cost >= 0) {
    maintenanceCosts.value[selectedEventId.value] = cost
    saveCosts()
    costEditorOpen.value = false
  }
}

const getMaintenanceCost = (eventId: string): number => maintenanceCosts.value[eventId] ?? 0
const calculateRoi = (monthlySavingsUsd: number, maintenanceCostUsd: number): number => {
  if (maintenanceCostUsd <= 0) return 0
  const yearlySavings = monthlySavingsUsd * 12
  return ((yearlySavings - maintenanceCostUsd) / maintenanceCostUsd) * 100
}

loadCosts()

// ═══ 圖表計算 ═══
// 回歸線計算
function calculateRegressionLine(data: Array<[number, number | null]>) {
  const validPoints = data.filter(([_, y]) => y !== null) as Array<[number, number]>
  if (validPoints.length < 2) return []

  const n = validPoints.length
  const sumX = validPoints.reduce((s, [x]) => s + x, 0)
  const sumY = validPoints.reduce((s, [, y]) => s + y, 0)
  const sumXY = validPoints.reduce((s, [x, y]) => s + x * y, 0)
  const sumX2 = validPoints.reduce((s, [x]) => s + x * x, 0)

  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX)
  const intercept = (sumY - slope * sumX) / n

  const minX = Math.min(...validPoints.map(([x]) => x))
  const maxX = Math.max(...validPoints.map(([x]) => x))

  return [
    [minX, intercept + slope * minX],
    [maxX, intercept + slope * maxX],
  ]
}

// 船殼 vs 螺旋槳貢獻百分比
const hullPct = computed(() => slData.value?.summary.hull_pct ?? 50)
const propPct = computed(() => slData.value?.summary.prop_pct ?? 50)

// Attribution 堆疊圖
const attributionOption = computed(() => {
  if (!slData.value) return {}
  const c = chart.value
  const smooth = slData.value.smooth

  // 從 smooth 陣列提取船殼和螺旋槳貢獻 (indices 2 & 3)
  const hullData = smooth.filter(s => s[1] !== null && s[1]! > 0).map(s => [s[0], s[2]])
  const propData = smooth.filter(s => s[1] !== null && s[1]! > 0).map(s => [s[0], s[3]])

  return {
    animation: false,
    grid: { left: 60, right: 20, top: 16, bottom: 50 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (params: any[]) => {
        const day = params[0]?.axisValue
        const hull = params.find((p: any) => p.seriesName === '船殼')?.value?.[1] ?? 0
        const prop = params.find((p: any) => p.seriesName === '螺旋槳')?.value?.[1] ?? 0
        return `Day ${day}<br/>船殼：${(hull as number)?.toFixed(3)} %<br/>螺旋槳：${(prop as number)?.toFixed(3)} %<br/>合計：${((hull as number) + (prop as number)).toFixed(2)} %`
      },
    },
    xAxis: {
      type: 'value',
      min: slData.value.day_min,
      max: slData.value.day_max,
      name: '相對天數',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 9 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      name: 'Speed Loss 貢獻 %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 9 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: '{value}%' },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: '船殼',
        type: 'line',
        stack: 'attribution',
        areaStyle: { color: '#E07B39', opacity: 0.65 },
        lineStyle: { width: 0 },
        itemStyle: { color: '#E07B39' },
        symbol: 'none',
        data: hullData,
        connectNulls: false,
      },
      {
        name: '螺旋槳',
        type: 'line',
        stack: 'attribution',
        areaStyle: { color: '#4A9B8E', opacity: 0.65 },
        lineStyle: { width: 0 },
        itemStyle: { color: '#4A9B8E' },
        symbol: 'none',
        data: propData,
        connectNulls: false,
      },
    ],
    legend: {
      data: ['船殼', '螺旋槳'],
      textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 11, color: c.inkSlate },
      bottom: 8,
    },
  }
})

// Speed Loss 趨勢圖
const trendOption = computed(() => {
  if (!slData.value) return {}
  const c = chart.value
  const raw = slData.value.raw
  const smooth = slData.value.smooth
  const events = slData.value.events

  const smoothLine = smooth.filter(s => s[1] !== null).map(s => [s[0], s[1]])
  const regressionLine = calculateRegressionLine(smooth)

  const EVENT_COLOR: Record<string, string> = {
    DD: '#A6672E', 'UWC+PP': '#E07B39', UWC: '#C8A84B', PP: '#4A9B8E', 'UWI+PP': '#6B9BB8', UWI: '#6B7A8D',
  }

  const markLineData = events.map(ev => ({
    xAxis: ev.day,
    lineStyle: { color: EVENT_COLOR[ev.type] ?? '#888', type: ev.is_uwi_only ? 'dotted' : 'dashed', width: 1.5 },
    label: {
      show: true,
      formatter: ev.type,
      color: EVENT_COLOR[ev.type] ?? '#888',
      fontSize: 9,
      fontFamily: 'IBM Plex Mono',
      position: 'insideEndTop',
    },
  }))

  return {
    animation: false,
    grid: { left: 60, right: 20, top: 16, bottom: 50 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (params: any[]) => {
        const day = params[0]?.axisValue
        const lines = params.map((p: any) => `${p.seriesName}：${p.value?.[1] != null ? p.value[1].toFixed(2) + ' %' : '—'}`)
        return `Day ${day}<br/>${lines.join('<br/>')}`
      },
    },
    xAxis: {
      type: 'value',
      min: slData.value.day_min,
      max: slData.value.day_max,
      name: '相對天數',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 9 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      name: 'Speed Loss %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 9 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: '{value}%' },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: '逐日原始點',
        type: 'scatter',
        data: raw,
        symbolSize: 3,
        itemStyle: { color: c.inkSlate, opacity: 0.25 },
        z: 1,
      },
      {
        name: '滾動中位數平滑',
        type: 'line',
        data: smoothLine,
        lineStyle: { width: 2.5, color: c.fathomTeal },
        itemStyle: { color: c.fathomTeal },
        symbol: 'none',
        connectNulls: false,
        z: 3,
        markLine: { symbol: 'none', silent: false, data: markLineData },
      },
      {
        name: '衰退趨勢線 (線性回歸)',
        type: 'line',
        data: regressionLine,
        lineStyle: { width: 1.5, color: c.brassAmber, type: 'dashed' },
        itemStyle: { color: c.brassAmber },
        symbol: 'none',
        z: 2,
      },
    ],
  }
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <StateDisplay
      v-if="slState !== 'success' || maintState !== 'success'"
      :state="slState === 'error' || maintState === 'error' ? 'error' : 'loading'"
      empty-title="載入中或無資料"
    />
    <template v-else-if="slData && maintData">
      <div class="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-4">
        <!-- 左側：Speed Loss 趨勢圖 -->
        <div class="panel p-3">
          <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">
            🚢 船體污損趨勢 — 灰色圓點 (原始) / 藍線 (平滑) / 琥珀虛線 (衰退趨勢預測)
          </p>
          <div class="h-[320px]">
            <VChart :option="trendOption" autoresize class="h-full w-full" />
          </div>
        </div>

        <!-- 右側：Tab 面板 -->
        <div class="panel p-4 flex flex-col">
          <div class="flex gap-1 mb-3 border-b border-[var(--color-ink-slate)]/20">
            <button
              v-for="tab in ['attribution', 'maintenance']"
              :key="tab"
              type="button"
              class="px-3 py-2 text-xs font-display tracking-wide transition-colors"
              :class="activeTab === tab ? 'text-[var(--color-brass-amber)] border-b-2 border-[var(--color-brass-amber)]' : 'text-[var(--color-ink-slate)]/60 hover:text-[var(--color-ink-slate)]'"
              @click="activeTab = tab as any"
            >
              {{ tab === 'attribution' ? '污損歸因' : '維修效能' }}
            </button>
          </div>

          <!-- Tab 1: 污損歸因 -->
          <div v-if="activeTab === 'attribution'" class="flex-1 overflow-y-auto space-y-3">
            <!-- 占比卡片 -->
            <div class="grid grid-cols-2 gap-2">
              <div class="panel p-3 border-l-4" style="border-left-color:#E07B39">
                <p class="text-[10px] text-[var(--color-ink-slate)]/60 mb-1">全期船殼貢獻</p>
                <p class="font-data text-2xl" style="color:#E07B39">{{ hullPct.toFixed(1) }}<span class="text-sm ml-0.5">%</span></p>
              </div>
              <div class="panel p-3 border-l-4" style="border-left-color:#4A9B8E">
                <p class="text-[10px] text-[var(--color-ink-slate)]/60 mb-1">全期螺旋槳貢獻</p>
                <p class="font-data text-2xl" style="color:#4A9B8E">{{ propPct.toFixed(1) }}<span class="text-sm ml-0.5">%</span></p>
              </div>
            </div>

            <!-- 堆疊圖 -->
            <div class="panel p-2">
              <p class="text-[10px] text-[var(--color-ink-slate)]/60 mb-1">時間序列：船殼（橙）vs 螺旋槳（綠）</p>
              <div class="h-[180px]">
                <VChart :option="attributionOption" autoresize class="h-full w-full" />
              </div>
            </div>

            <!-- 方法論摘要 -->
            <div class="text-[9px] text-[var(--color-ink-slate)]/50 bg-[var(--color-ink-slate)]/[0.02] p-2 rounded border border-[var(--color-ink-slate)]/10">
              <p class="font-display font-semibold mb-1">啟發式估計</p>
              <ul class="list-disc list-inside space-y-0.5">
                <li>船殼：FOC 對週期基準偏離 %</li>
                <li>螺旋槳：SLIP 超出 p5 基準</li>
              </ul>
            </div>
          </div>

          <!-- Tab 2: 維修效能 + ROI -->
          <div v-if="activeTab === 'maintenance'" class="flex-1 overflow-y-auto">
            <p class="text-xs text-[var(--color-ink-slate)]/70 mb-2">最近維修事件</p>
            <div v-if="maintData.events && maintData.events.length > 0" class="space-y-2 max-h-64 overflow-y-auto">
              <div v-for="evt in maintData.events.slice(0, 3)" :key="evt.id" class="text-xs border-l-2 border-[var(--color-brass-amber)] pl-2 py-1">
                <p class="font-bold">Day {{ evt.day }}</p>
                <p class="text-[var(--color-ink-slate)]/70">{{ evt.type }}</p>
                <p class="text-[var(--color-fathom-teal)]">月節省: {{ formatUsd(evt.monthlySavingsUsd) }}</p>
                <p class="text-xs text-[var(--color-ink-slate)]/50" v-if="evt.isAnomaly">⚠️ 異常</p>
              </div>
            </div>
          </div>

        </div>
      </div>

      <!-- 底部：維修事件表 -->
      <div class="panel p-4">
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">養護事件效益驗證明細</p>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-[var(--color-ink-slate)]/20 text-left text-xs text-[var(--color-ink-slate)]/60">
                <th class="py-2 pr-3">Day</th>
                <th class="py-2 pr-3">類型</th>
                <th class="py-2 pr-3 text-right">SL改善</th>
                <th class="py-2 pr-3 text-right text-[var(--color-brass-amber)]">節省/月</th>
                <th class="py-2 pr-3 text-right">維修成本</th>
                <th class="py-2 pr-3 text-right text-[var(--color-fathom-teal)]">ROI %</th>
                <th class="py-2 pr-3 text-center">狀態</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="evt in maintData.events" :key="evt.id" class="border-b border-[var(--color-ink-slate)]/8 hover:bg-[var(--color-ink-slate)]/5" :class="{ 'bg-[var(--color-signal-red)]/5': evt.isAnomaly }">
                <td class="py-2 pr-3 font-data">{{ formatDay(evt.day) }}</td>
                <td class="py-2 pr-3">{{ evt.type }}</td>
                <td class="py-2 pr-3 text-right font-data text-[var(--color-fathom-teal)]">{{ (evt.speedLossAfter - evt.speedLossBefore).toFixed(1) }}%</td>
                <td class="py-2 pr-3 text-right font-data text-[var(--color-brass-amber)] font-semibold">{{ formatUsd(evt.monthlySavingsUsd) }}</td>
                <td class="py-2 pr-3 text-right">
                  <button
                    type="button"
                    class="font-data text-xs px-2 py-1 rounded border border-[var(--color-ink-slate)]/30 hover:border-[var(--color-brass-amber)] hover:bg-[var(--color-brass-amber)]/10 transition-colors"
                    @click="openCostEditor(evt.id, getMaintenanceCost(evt.id))"
                  >
                    {{ getMaintenanceCost(evt.id) > 0 ? formatUsd(getMaintenanceCost(evt.id)) : '新增' }}
                  </button>
                </td>
                <td class="py-2 pr-3 text-right font-data" :class="calculateRoi(evt.monthlySavingsUsd, getMaintenanceCost(evt.id)) > 0 ? 'text-[var(--color-fathom-teal)]' : 'text-[var(--color-ink-slate)]/40'">
                  {{ getMaintenanceCost(evt.id) > 0 ? calculateRoi(evt.monthlySavingsUsd, getMaintenanceCost(evt.id)).toFixed(0) + '%' : '—' }}
                </td>
                <td class="py-2 pr-3 text-center">
                  <span v-if="evt.isAnomaly" class="text-[var(--color-signal-red)]" :title="evt.anomalyReason ?? ''">❌</span>
                  <span v-else class="text-[var(--color-fathom-teal)]">✅</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 維修成本編輯 Modal -->
      <div v-if="costEditorOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
        <div class="bg-white dark:bg-[var(--color-marine-navy)] rounded-lg shadow-lg p-6 max-w-sm w-full mx-4">
          <h2 class="text-lg font-bold mb-4">填入維修成本</h2>
          <div class="mb-4">
            <label class="block text-sm text-[var(--color-ink-slate)]/70 mb-2">維修成本 (USD)</label>
            <input v-model="maintenanceCostInput" type="number" min="0" step="1000" placeholder="例：50000" class="w-full px-3 py-2 border border-[var(--color-ink-slate)]/30 rounded focus:outline-none focus:border-[var(--color-brass-amber)]" />
          </div>
          <div class="flex gap-2 justify-end">
            <button type="button" class="px-4 py-2 rounded border border-[var(--color-ink-slate)]/30 hover:bg-[var(--color-ink-slate)]/5" @click="costEditorOpen = false">
              取消
            </button>
            <button type="button" class="px-4 py-2 rounded bg-[var(--color-brass-amber)] text-white hover:bg-[var(--color-brass-amber)]/80" @click="saveCostForEvent">
              保存
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
