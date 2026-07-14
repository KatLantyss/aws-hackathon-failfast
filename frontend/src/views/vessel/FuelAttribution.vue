<script setup lang="ts">
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import { fetchFuelAttribution } from '@/mock/api'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import { CONFIDENCE_LABEL, formatDate } from '@/utils/format'
import { useChartTheme } from '@/composables/useChartTheme'
import { useFuelWaterfallOption, fuelFactorColors } from '@/composables/useFuelWaterfallOption'

const CATEGORY_LABEL: Record<string, string> = {
  'hull+propeller': '船體+螺旋槳（複合事件）',
  hull: '船體',
  propeller: '螺旋槳',
  inspection_only: '純檢查（無實體介入）',
  other: '其他',
}

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data, state } = useAsyncData(() => props.imo, fetchFuelAttribution)
const chart = useChartTheme()

const view = ref<'timeseries' | 'stacked'>('timeseries')

const FACTOR_COLORS = computed(() => fuelFactorColors(chart.value))

// --- Waterfall: baseline -> +weather -> +hull -> +propeller -> +engine -> actual
const waterfallOption = useFuelWaterfallOption(data, chart)

// --- SHAP-style horizontal bar (already sorted by impact desc)
const shapOption = computed(() => {
  if (!data.value) return {}
  const c = chart.value
  const factorColors = FACTOR_COLORS.value
  const sorted = [...data.value.attribution].sort((a, b) => b.impactMt - a.impactMt)
  return {
    animation: false,
    grid: { left: 110, right: 32, top: 16, bottom: 24 },
    tooltip: {
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (p: any) => `${p.name}: ${p.value.toFixed(2)} MT/日`,
    },
    xAxis: {
      type: 'value',
      name: 'MT/日',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    yAxis: {
      type: 'category',
      data: sorted.map((a) => a.label),
      axisLabel: { fontFamily: 'IBM Plex Sans', fontSize: 11, color: c.inkSlate },
    },
    series: [
      {
        type: 'bar',
        data: sorted.map((a) => ({ value: a.impactMt, itemStyle: { color: factorColors[a.factor] } })),
        barWidth: '55%',
        label: { show: true, position: 'right', formatter: (p: any) => p.value.toFixed(2), fontFamily: 'IBM Plex Mono', fontSize: 11 },
      },
    ],
  }
})

// --- stacked area over time
const stackedOption = computed(() => {
  if (!data.value) return {}
  const c = chart.value
  const factorColors = FACTOR_COLORS.value
  const factors: (keyof typeof factorColors)[] = ['weather', 'hull_fouling', 'propeller_fouling', 'engine_degradation']
  const labels: Record<string, string> = {
    weather: '天氣（風浪）',
    hull_fouling: '船體污損',
    propeller_fouling: '螺旋槳污損',
    engine_degradation: '主機老化',
  }
  return {
    animation: false,
    grid: { left: 56, right: 24, top: 40, bottom: 40 },
    legend: { top: 4, textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 11, color: c.inkSlate } },
    tooltip: { trigger: 'axis', backgroundColor: c.marineNavy, textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 } },
    xAxis: {
      type: 'time',
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    yAxis: {
      type: 'value',
      name: 'MT/日',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: factors.map((f) => ({
      name: labels[f],
      type: 'line',
      stack: 'total',
      areaStyle: { color: factorColors[f], opacity: 0.75 },
      lineStyle: { color: factorColors[f], width: 1 },
      showSymbol: false,
      data: data.value!.timeSeries.map((p) => [p.date, (p as any)[f]]),
    })),
  }
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <StateDisplay
      v-if="state !== 'success'"
      :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
      empty-title="此船尚無油耗歸因資料"
    />
    <template v-else-if="data">
      <div class="flex items-center justify-between">
        <PanelTag code="FUEL-A1" />
        <span
          class="text-xs px-2 py-1 rounded-[2px] border font-data"
          :class="data.confidence === 'high' ? 'border-[var(--color-fathom-teal)] text-[var(--color-fathom-teal)]' : 'border-[var(--color-brass-amber)] text-[var(--color-brass-amber)]'"
        >
          信心程度: {{ CONFIDENCE_LABEL[data.confidence] }}
        </span>
      </div>

      <div class="panel p-3">
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">油耗差異拆解（瀑布圖）</p>
        <div class="h-[320px]">
          <VChart :option="waterfallOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="panel p-3">
          <PanelTag code="FUEL-A2" class="mb-2" />
          <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">特徵平均影響排序</p>
          <div class="h-[240px]">
            <VChart :option="shapOption" autoresize class="h-full w-full" />
          </div>
        </div>

        <div class="panel p-3">
          <div class="flex items-center justify-between mb-2">
            <PanelTag code="FUEL-A3" />
            <div class="flex gap-1 text-xs">
              <button
                class="px-2 py-1 rounded-[2px] border font-display uppercase tracking-wide"
                :class="view === 'timeseries' ? 'bg-[var(--color-brass-amber)] text-white border-[var(--color-brass-amber)]' : ''"
                @click="view = 'timeseries'"
              >
                堆疊面積圖
              </button>
            </div>
          </div>
          <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">
            各歸因因子隨時間變化（最近 60 筆）
          </p>
          <div class="h-[240px]">
            <VChart :option="stackedOption" autoresize class="h-full w-full" />
          </div>
        </div>
      </div>

      <div class="panel p-4">
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">白話解釋</p>
        <ul class="flex flex-col gap-1.5 text-sm">
          <li v-for="a in data.attribution" :key="a.factor" class="flex items-center gap-2">
            <span class="status-dot" :style="{ background: FACTOR_COLORS[a.factor] }" />
            本趟因{{ a.label }}多燒了 {{ a.impactMt.toFixed(2) }} 噸燃油，約占超額油耗的
            {{ (((a.impactMt) / (data.actualFuelMt - data.baselineFuelMt)) * 100).toFixed(0) }}%。
          </li>
        </ul>
      </div>

      <!-- Real backend evidence: per-event before/after slip% from
           GET /speed-loss-attribution, with the UWI "control group" cases
           (no physical intervention) called out — the model should NOT
           show meaningful improvement for those. -->
      <div class="panel p-4">
        <div class="flex items-center justify-between mb-2">
          <PanelTag code="FUEL-A4" />
          <span class="text-xs font-data text-[var(--color-ink-slate)]/50">{{ data.method }}</span>
        </div>
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">
          養護事件實測前後 Speed Loss 變化（真實資料，非模擬）
        </p>
        <StateDisplay v-if="!data.events.length" state="empty" empty-title="此船尚無可比對的養護事件紀錄" />
        <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-2.5">
          <div
            v-for="ev in data.events"
            :key="ev.eventType + ev.date"
            class="rounded-[2px] border p-3 text-sm"
            :class="
              ev.physicalIntervention
                ? 'chart-divider'
                : 'border-dashed border-[var(--color-ink-slate)]/30 bg-[var(--color-ink-slate)]/[0.03]'
            "
          >
            <div class="flex items-center justify-between mb-1">
              <span class="font-display text-xs">{{ ev.eventType }} · {{ formatDate(ev.date) }}</span>
              <span
                class="text-[10px] px-1.5 py-0.5 rounded-[2px] border font-body"
                :class="ev.physicalIntervention ? '' : 'text-[var(--color-ink-slate)]/60'"
              >
                {{ CATEGORY_LABEL[ev.category] ?? ev.category }}
              </span>
            </div>
            <p class="font-data text-xs text-[var(--color-ink-slate)]/70">
              Slip {{ ev.slipBeforePct.toFixed(1) }}% → {{ ev.slipAfterPct.toFixed(1) }}%
              <span :class="ev.slipDeltaPct > 0 ? 'text-[var(--color-fathom-teal)]' : 'text-[var(--color-signal-red)]'" class="font-semibold">
                ({{ ev.slipDeltaPct > 0 ? '−' : '+' }}{{ Math.abs(ev.slipDeltaPct).toFixed(2) }}pp{{ ev.slipDeltaPct > 0 ? ' 改善' : ' 未改善' }})
              </span>
            </p>
            <p v-if="!ev.physicalIntervention" class="text-xs text-[var(--color-ink-slate)]/60 mt-1">
              ⓘ 此事件僅為檢查，未進行實體清洗/拋光 — 若模型判讀合理，Slip 變化應接近 0（控制組驗證）。
            </p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
