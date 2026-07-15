<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import { getFuelAnomalyCause, type FuelAnomalyCause } from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { useChartTheme } from '@/composables/useChartTheme'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data, state } = useAsyncData(() => props.imo, getFuelAnomalyCause)
const chart = useChartTheme()

const dsSummary: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/fuel-anomaly-cause',
  description:
    '逐日油耗異常根因分類：先用只看操作條件（轉速/船速/吃水/載重/天氣）的模型算出「預期油耗」，' +
    '實際與預期差距超過門檻視為異常，再用 SHAP 拆解出船殼/螺旋槳/天候各自的貢獻，取最大的當主因。' +
    '完整方法與驗證見 notebooks/anomaly_analysis.ipynb §6-9。',
  fields: [
    { ui: '各成因天數', source: 'summary.cause_breakdown / summary.confident_cause_breakdown' },
    { ui: '基準模型 R²', source: 'baseline_model_r2' },
  ],
}
const dsBar: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/fuel-anomaly-cause',
  description:
    '每一天的油耗殘差 %，顏色=主因分類。半透明的長條代表 cause_model_agrees=false' +
    '（根因模型跟基準模型對這天的異常方向判斷不一致，分類不可信，僅供參考）。',
  fields: [
    { ui: '長條高度 / 顏色 / 透明度', source: 'anomalies[].residual_pct, primary_cause, cause_model_agrees' },
  ],
}
const dsTable: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/fuel-anomaly-cause',
  description: '異常明細表，anomalies[] 全欄位原樣顯示（最近 20 筆）。',
  fields: [
    { ui: '實際/預期油耗、殘差 %、主因、養護天數', source: 'anomalies[].*' },
  ],
}

// Cause color/label map
const CAUSE_COLORS: Record<FuelAnomalyCause, string> = {
  船殼汙損: '#E07B39',
  螺旋槳汙損: '#C8A84B',
  天候: '#6B7A8D',
}

const summaryEntries = computed(() => {
  if (!data.value) return []
  const total = data.value.summary.cause_breakdown
  const confident = data.value.summary.confident_cause_breakdown
  return (Object.keys(total) as FuelAnomalyCause[])
    .map((cause) => ({
      cause,
      color: CAUSE_COLORS[cause] ?? '#6B7A8D',
      count: total[cause] ?? 0,
      confidentCount: confident[cause] ?? 0,
    }))
    .sort((a, b) => b.count - a.count)
})

// Bar chart: residual_pct per anomaly day, colored by primary_cause
const anomalyBarOption = computed(() => {
  if (!data.value || !data.value.anomalies.length) return {}
  const c = chart.value
  const rows = [...data.value.anomalies].sort((a, b) => a.noon_day - b.noon_day)
  return {
    animation: false,
    grid: { left: 64, right: 32, top: 16, bottom: 60 },
    tooltip: {
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (p: any) => {
        const r = rows[p.dataIndex]
        const confidence = r.cause_model_agrees === false ? '（低信心）' : ''
        return `Day ${r.noon_day}<br/>實際 ${r.daily_foc_actual} MT/day → 預期 ${r.daily_foc_expected} MT/day<br/>殘差: ${r.residual_pct > 0 ? '+' : ''}${r.residual_pct.toFixed(1)}%<br/>主因: ${r.primary_cause ?? '—'}${confidence}`
      },
    },
    xAxis: {
      type: 'category',
      data: rows.map((r) => `D${r.noon_day}`),
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 9, color: c.inkSlate, interval: 0, rotate: 45 },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    yAxis: {
      type: 'value',
      name: '油耗殘差 %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        type: 'bar',
        data: rows.map((r) => ({
          value: r.residual_pct,
          itemStyle: {
            color: r.primary_cause ? CAUSE_COLORS[r.primary_cause] ?? c.fathomTeal : c.fathomTeal,
            opacity: r.cause_model_agrees === false ? 0.35 : 1,
          },
        })),
        barMaxWidth: 20,
      },
    ],
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
      <!-- Summary by cause -->
      <div class="panel p-4">
        <DataSourceTag :info="dsSummary" />
        <PanelTag code="FUEL-A1" class="mb-3" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">
          近 {{ data.summary.total_days_analyzed }} 個穩態日，{{ data.summary.anomaly_days }} 天油耗異常（基準模型 R²={{ data.baseline_model_r2?.toFixed(3) ?? '—' }}）
        </p>
        <div v-if="summaryEntries.length" class="grid grid-cols-3 gap-3">
          <div v-for="s in summaryEntries" :key="s.cause" class="panel p-3 border-l-4" :style="{ borderLeftColor: s.color }">
            <p class="font-display text-xs text-[var(--color-ink-slate)]/60 mb-1">{{ s.cause }}</p>
            <p class="font-data text-xl" :style="{ color: s.color }">{{ s.count }} 天</p>
            <p class="font-mono text-[10px] text-[var(--color-ink-slate)]/50 mt-0.5">其中 {{ s.confidentCount }} 天可信</p>
          </div>
        </div>
        <p v-else class="text-sm text-[var(--color-ink-slate)]/60">近期沒有偵測到油耗異常。</p>
      </div>

      <!-- Anomaly bar chart -->
      <div v-if="data.anomalies.length" class="panel p-3">
        <DataSourceTag :info="dsBar" />
        <PanelTag code="FUEL-A2" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">每日油耗殘差 %（顏色=主因，半透明=低信心）</p>
        <div class="h-[280px]">
          <VChart :option="anomalyBarOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <!-- Anomaly details table -->
      <div v-if="data.anomalies.length" class="panel p-3 overflow-x-auto">
        <DataSourceTag :info="dsTable" />
        <PanelTag code="FUEL-A3" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">異常明細（最近 {{ data.anomalies.length }} 筆）</p>
        <table class="w-full text-sm min-w-[720px]">
          <thead>
            <tr class="chart-divider">
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">Day</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">實際 MT/day</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">預期 MT/day</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">殘差 %</th>
              <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">主因</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">距清船殼</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">距拋螺旋槳</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="a in data.anomalies"
              :key="a.noon_day"
              class="chart-divider hover:bg-black/[0.02]"
              :class="{ 'opacity-40': a.cause_model_agrees === false }"
            >
              <td class="px-3 py-1.5 font-data text-right">{{ a.noon_day }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ a.daily_foc_actual.toFixed(1) }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ a.daily_foc_expected.toFixed(1) }}</td>
              <td
                class="px-3 py-1.5 font-data text-right font-semibold"
                :class="a.residual_pct >= 0 ? 'text-[var(--color-signal-red)]' : 'text-[var(--color-fathom-teal)]'"
              >
                {{ a.residual_pct >= 0 ? '+' : '' }}{{ a.residual_pct.toFixed(1) }}%
              </td>
              <td class="px-3 py-1.5">
                <span
                  v-if="a.primary_cause"
                  class="text-xs px-1.5 py-0.5 rounded-[2px] font-body"
                  :style="{ background: `${CAUSE_COLORS[a.primary_cause]}22`, color: CAUSE_COLORS[a.primary_cause] }"
                >{{ a.primary_cause }}</span>
                <span v-else class="text-xs text-[var(--color-ink-slate)]/40">—</span>
                <span v-if="a.cause_model_agrees === false" class="text-[10px] text-[var(--color-ink-slate)]/40 ml-1">(低信心)</span>
              </td>
              <td class="px-3 py-1.5 font-data text-right">{{ a.days_since_hull_clean }}d</td>
              <td class="px-3 py-1.5 font-data text-right">{{ a.days_since_prop_polish }}d</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
