<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import { fetchRecommendation } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import MaintenanceRecommendationCard from '@/components/MaintenanceRecommendationCard.vue'
import { useChartTheme } from '@/composables/useChartTheme'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data, state } = useAsyncData(() => props.imo, fetchRecommendation)
const chart = useChartTheme()

const chartOption = computed(() => {
  if (!data.value) return {}
  const c = chart.value
  const curve = data.value.curve
  return {
    animation: false,
    grid: { left: 64, right: 24, top: 24, bottom: 48 },
    legend: { top: 0, textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 11, color: c.inkSlate } },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      valueFormatter: (v: number) => `$${v.toLocaleString()}`,
    },
    xAxis: {
      type: 'value',
      name: '延後維修天數',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    yAxis: {
      type: 'value',
      name: 'USD',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: (v: number) => `$${(v / 1000).toFixed(0)}k` },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: '累積超額油耗成本',
        type: 'line',
        showSymbol: false,
        lineStyle: { color: c.signalRed, width: 2 },
        data: curve.map((p) => [p.deferralDays, p.cumulativeExcessFuelCostUsd]),
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
      empty-title="此船尚無維修建議資料"
    />
    <template v-else-if="data">
      <div class="panel p-3">
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">成本效益模擬曲線</p>
        <div class="h-[360px]">
          <VChart :option="chartOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        <MaintenanceRecommendationCard :data="data" />

        <div v-if="data.dataLimitations.length" class="panel p-4 border-l-4" style="border-left-color: var(--color-signal-red)">
          <p class="font-display text-sm mb-2 text-[var(--color-signal-red)]">未盡之處</p>
          <ul class="flex flex-col gap-1.5 text-sm">
            <li v-for="(item, i) in data.dataLimitations" :key="i" class="flex gap-2">
              <span>⚠</span>
              <span>{{ item }}</span>
            </li>
          </ul>
        </div>
        <div v-else class="panel p-4 flex items-center justify-center text-sm text-[var(--color-ink-slate)]/60">
          資料量充足，建議信心程度高。
        </div>
      </div>
    </template>
  </div>
</template>
