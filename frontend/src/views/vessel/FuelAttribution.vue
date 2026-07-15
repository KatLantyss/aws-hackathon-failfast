<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import { getSpeedLossAttribution } from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { useChartTheme } from '@/composables/useChartTheme'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data, state } = useAsyncData(() => props.imo, getSpeedLossAttribution)
const chart = useChartTheme()

const ISO_NOTE =
  'ISO 19030 對應：本頁對應主需求「② Speed Loss 有多少百分比因船體髒污所致（船殼 vs 螺旋槳歸因）」，做的是速損（Slip%）歸因，不是燃油消耗來源拆解——導覽列已改標「速損歸因」對齊實際內容（原「油耗歸因」為誤標，已修正）。'

const dsSummary: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/speed-loss-attribution',
  description: `分類卡直接來自 summary 欄位，無前端加工。${ISO_NOTE}`,
  fields: [
    { ui: '各分類平均改善 %', source: 'summary["hull+propeller"|"hull"|"propeller"|"inspection_only"|"other"]' },
  ],
}
const dsBar: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/speed-loss-attribution',
  description: '事件前後 Slip 差值長條圖，欄位原樣使用。同 FUEL-A1 的 ISO 19030 對應說明。',
  fields: [
    { ui: '長條高度 / 顏色', source: 'event_attributions[].slip_delta_pct, category' },
    { ui: 'tooltip 前/後值', source: 'event_attributions[].slip_before_pct / slip_after_pct' },
  ],
}
const dsTable: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/speed-loss-attribution',
  description: '事件明細表，event_attributions[] 全欄位原樣顯示。',
  fields: [
    { ui: '事件類型 / 歸因類別 / 事件日', source: 'event_type / category / event_day' },
    { ui: '前/後 Slip % / 改善 %', source: 'slip_before_pct / slip_after_pct / slip_delta_pct' },
  ],
}
const dsWeather: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/speed-loss-attribution',
  description: '天候代理指標時序圖，直接繪製 weather_timeline 原始點位。',
  fields: [
    { ui: '散布點 (Day, STW-SOG Slip%)', source: 'weather_timeline[].noon_day / diff_stw_sog' },
  ],
}

// Category color map
const CATEGORY_COLORS: Record<string, string> = {
  'hull+propeller': '#C94B4B',
  hull: '#E07B39',
  propeller: '#C8A84B',
  inspection_only: '#8FA6B2',
  other: '#6B7A8D',
}
const CATEGORY_LABELS: Record<string, string> = {
  'hull+propeller': '船殼+螺旋槳',
  hull: '船殼',
  propeller: '螺旋槳',
  inspection_only: '純檢查（無預期改善）',
  other: '其他',
}

// Bar chart: maintenance events — slip delta per event
const eventBarOption = computed(() => {
  if (!data.value) return {}
  const c = chart.value
  const events = data.value.event_attributions.filter((e) => e.slip_delta_pct !== null)
  return {
    animation: false,
    grid: { left: 80, right: 32, top: 16, bottom: 60 },
    tooltip: {
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (p: any) => {
        const e = events[p.dataIndex]
        return `${e.event_type} (Day ${e.event_day})<br/>前: ${e.slip_before_pct?.toFixed(1)}% → 後: ${e.slip_after_pct?.toFixed(1)}%<br/>改善: ${e.slip_delta_pct?.toFixed(2)}%`
      },
    },
    xAxis: {
      type: 'category',
      data: events.map((e) => `${e.event_type}\nD${e.event_day}`),
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, interval: 0 },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    yAxis: {
      type: 'value',
      name: 'Slip 改善 %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        type: 'bar',
        data: events.map((e) => ({
          value: e.slip_delta_pct,
          itemStyle: {
            color: (e.slip_delta_pct ?? 0) >= 0 ? CATEGORY_COLORS[e.category] ?? c.fathomTeal : c.signalRed,
          },
        })),
        barMaxWidth: 36,
        label: {
          show: true,
          position: 'top',
          formatter: (p: any) => (p.value != null ? `${Number(p.value).toFixed(1)}%` : ''),
          fontFamily: 'IBM Plex Mono',
          fontSize: 10,
        },
      },
    ],
  }
})

// Weather proxy timeline: DIFF_STW_SOG_SLIP
const weatherTimelineOption = computed(() => {
  if (!data.value || !data.value.weather_timeline.length) return {}
  const c = chart.value
  const pts = data.value.weather_timeline
  return {
    animation: false,
    grid: { left: 56, right: 24, top: 16, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (p: any) => `Day ${p[0].value[0]}<br/>STW-SOG Slip: ${p[0].value[1].toFixed(2)}%`,
    },
    xAxis: {
      type: 'value',
      name: 'Noon Day',
      nameLocation: 'middle',
      nameGap: 24,
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    yAxis: {
      type: 'value',
      name: 'Slip %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        type: 'scatter',
        symbolSize: 3,
        itemStyle: { color: '#8FA6B2', opacity: 0.7 },
        data: pts.map((p) => [p.noon_day, p.diff_stw_sog]),
      },
    ],
  }
})

// Summary table: avg improvement per category
const summaryEntries = computed(() => {
  if (!data.value) return []
  return Object.entries(data.value.summary).map(([cat, avg]) => ({
    category: cat,
    label: CATEGORY_LABELS[cat] ?? cat,
    avgDelta: avg as number,
    color: CATEGORY_COLORS[cat] ?? '#6B7A8D',
  })).sort((a, b) => b.avgDelta - a.avgDelta)
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <StateDisplay
      v-if="state !== 'success'"
      :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
      empty-title="此船尚無速損歸因資料"
    />
    <template v-else-if="data">
      <!-- Summary by category -->
      <div v-if="summaryEntries.length" class="panel p-4">
        <DataSourceTag :info="dsSummary" />
        <PanelTag code="FUEL-A1" class="mb-3" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">各養護類別平均 Speed Loss 改善幅度</p>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div v-for="s in summaryEntries" :key="s.category" class="panel p-3 border-l-4" :style="{ borderLeftColor: s.color }">
            <p class="font-display text-xs text-[var(--color-ink-slate)]/60 mb-1">{{ s.label }}</p>
            <p class="font-data text-xl" :style="{ color: s.color }">{{ s.avgDelta.toFixed(2) }}%</p>
            <p class="font-mono text-[10px] text-[var(--color-ink-slate)]/50 mt-0.5">平均 Slip 下降</p>
          </div>
        </div>
      </div>

      <!-- Event attribution bar chart -->
      <div class="panel p-3">
        <DataSourceTag :info="dsBar" />
        <PanelTag code="FUEL-A2" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">各養護事件前後 Speed Loss 差值（正值 = 改善）</p>
        <div class="h-[280px]">
          <VChart :option="eventBarOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <!-- Event details table -->
      <div class="panel p-3 overflow-x-auto">
        <DataSourceTag :info="dsTable" />
        <PanelTag code="FUEL-A3" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">養護事件明細</p>
        <table class="w-full text-sm min-w-[640px]">
          <thead>
            <tr class="chart-divider">
              <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">事件類型</th>
              <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">歸因類別</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">事件日</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">前 Slip %</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">後 Slip %</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">改善 %</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="e in data.event_attributions"
              :key="`${e.event_type}-${e.event_day}`"
              class="chart-divider hover:bg-black/[0.02]"
            >
              <td class="px-3 py-1.5 font-data">{{ e.event_type }}</td>
              <td class="px-3 py-1.5">
                <span
                  class="text-xs px-1.5 py-0.5 rounded-[2px] font-body"
                  :style="{ background: `${CATEGORY_COLORS[e.category]}22`, color: CATEGORY_COLORS[e.category] }"
                >{{ CATEGORY_LABELS[e.category] ?? e.category }}</span>
              </td>
              <td class="px-3 py-1.5 font-data text-right">{{ e.event_day }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ e.slip_before_pct?.toFixed(2) ?? '—' }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ e.slip_after_pct?.toFixed(2) ?? '—' }}</td>
              <td
                class="px-3 py-1.5 font-data text-right font-semibold"
                :class="(e.slip_delta_pct ?? 0) >= 0 ? 'text-[var(--color-fathom-teal)]' : 'text-[var(--color-signal-red)]'"
              >
                {{ e.slip_delta_pct != null ? `${e.slip_delta_pct >= 0 ? '+' : ''}${e.slip_delta_pct.toFixed(2)}%` : '—' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Weather proxy timeline -->
      <div v-if="data.weather_timeline.length" class="panel p-3">
        <DataSourceTag :info="dsWeather" />
        <PanelTag code="FUEL-A4" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">洋流/天候影響代理指標（DIFF_STW_SOG）</p>
        <div class="h-[200px]">
          <VChart :option="weatherTimelineOption" autoresize class="h-full w-full" />
        </div>
      </div>
    </template>
  </div>
</template>
