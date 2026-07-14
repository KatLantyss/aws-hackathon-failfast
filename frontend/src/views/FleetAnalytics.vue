<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import VChart from 'vue-echarts'
import { useRouter } from 'vue-router'
import { fetchFleetVessels, fetchNoonReportSeries } from '@/mock/api'
import type { NoonReportEntry } from '@/types/fleet'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import { formatUsd, URGENCY_LABEL, URGENCY_COLOR } from '@/utils/format'
import { useChartTheme } from '@/composables/useChartTheme'

const router = useRouter()
const { data: vessels, state } = useAsyncData(() => true, fetchFleetVessels)
const chart = useChartTheme()

const sortKey = ref<'speedLossPct' | 'excessFuelCostUsdMtd' | 'urgency'>('speedLossPct')

const urgencyRank: Record<string, number> = { HIGH: 3, MEDIUM: 2, LOW: 1 }

const ranked = computed(() => {
  if (!vessels.value) return []
  return [...vessels.value].sort((a, b) => {
    if (sortKey.value === 'urgency') return urgencyRank[b.maintenanceUrgency] - urgencyRank[a.maintenanceUrgency]
    return b[sortKey.value] - a[sortKey.value]
  })
})

// Per-vessel noon-report series for the overlay chart, fetched once the
// fleet list resolves (real backend data, not the old synthetic generator).
const seriesByVessel = ref<Map<string, NoonReportEntry[]>>(new Map())
watchEffect(async () => {
  if (!vessels.value) return
  const entries = await Promise.all(vessels.value.map(async (v) => [v.imo, await fetchNoonReportSeries(v.imo)] as const))
  seriesByVessel.value = new Map(entries)
})

const overlayOption = computed(() => {
  if (!vessels.value) return {}
  const c = chart.value
  const colors = [c.brassAmber, c.fathomTeal, c.signalRed, c.inkSlate, '#8FA6B2']
  const series = vessels.value.map((v, i) => {
    const reports = seriesByVessel.value.get(v.imo) ?? []
    const points = reports.slice(-180).map((r) => [r.date, r.speedLossPct])
    return {
      name: v.name,
      type: 'line' as const,
      showSymbol: false,
      lineStyle: { color: colors[i % colors.length], width: 1.5 },
      data: points,
    }
  })
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
      name: 'Speed Loss %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: '{value}%' },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series,
  }
})

function exportReport() {
  window.alert('月報 PDF 匯出為示意功能，正式版將串接後端報表產生服務。')
}

function goToVessel(imo: string) {
  router.push(`/vessels/${imo}/overview`)
}
</script>

<template>
  <div class="mx-auto max-w-[1440px] px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p class="panel-tag w-fit mb-2">FLEET-01</p>
        <h1 class="text-2xl">跨船隊分析</h1>
      </div>
      <button
        class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
        @click="exportReport"
      >
        匯出月報 PDF
      </button>
    </div>

    <StateDisplay v-if="state !== 'success'" :state="state === 'error' ? 'error' : 'loading'" />
    <template v-else>
      <div class="panel p-3">
        <PanelTag code="OVL-01" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">
          同型船污損曲線疊圖比較（最近 180 筆 Noon Report）
        </p>
        <div class="h-[360px]">
          <VChart :option="overlayOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <div class="panel p-3">
        <div class="flex items-center justify-between mb-2">
          <PanelTag code="RANK-02" />
          <label class="flex items-center gap-2 text-xs">
            <span class="text-[var(--color-ink-slate)]/60">排序依據</span>
            <select v-model="sortKey" class="border rounded-[2px] px-2 py-1">
              <option value="speedLossPct">Speed Loss</option>
              <option value="excessFuelCostUsdMtd">超額油耗成本</option>
              <option value="urgency">維修急迫度</option>
            </select>
          </label>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm min-w-[640px]">
            <thead>
              <tr class="chart-divider">
                <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">排名</th>
                <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">船名</th>
                <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">船型</th>
                <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">Speed Loss %</th>
                <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">超額油耗成本 (月)</th>
                <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">維修急迫度</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(v, i) in ranked"
                :key="v.imo"
                class="chart-divider hover:bg-black/[0.02] cursor-pointer"
                @click="goToVessel(v.imo)"
              >
                <td class="px-3 py-2 font-data">{{ i + 1 }}</td>
                <td class="px-3 py-2 font-display">{{ v.name }}</td>
                <td class="px-3 py-2">{{ v.type }}</td>
                <td class="px-3 py-2 font-data text-right">{{ v.speedLossPct.toFixed(1) }}%</td>
                <td class="px-3 py-2 font-data text-right">{{ formatUsd(v.excessFuelCostUsdMtd) }}</td>
                <td class="px-3 py-2">
                  <span class="font-semibold" :style="{ color: URGENCY_COLOR[v.maintenanceUrgency] }">
                    {{ URGENCY_LABEL[v.maintenanceUrgency] }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
