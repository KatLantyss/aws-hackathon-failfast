<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { useRouter } from 'vue-router'
import { fetchVessels, fetchSpeedLossData } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { formatUsd, URGENCY_LABEL, URGENCY_COLOR } from '@/utils/format'
import { useChartTheme } from '@/composables/useChartTheme'
import type { SpeedLossSeries } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'

const router = useRouter()
const { data: vessels, state } = useAsyncData(() => true, fetchVessels)
const chart = useChartTheme()

const dsOverlay: DataSourceInfo = {
  status: 'real',
  endpoint: ['GET /api/v1/fleet/summary', 'GET /api/v1/vessels/{vessel_id}/speed-loss ×N'],
  description: '每艘船的曲線都是真實資料，但實作上是對「每一艘船」各自呼叫一次 speed-loss（+maintenance-events），15 艘船 = 一次載入約 30 個 request（N+1 模式）。船隊變多時載入會變慢，值得之後改成後端批次端點。',
  fields: [
    { ui: '每條曲線的 (Day, Slip%) 點', source: 'per-vessel iso_timeline / slip_timeline，取最近 180 筆' },
  ],
}

const dsRanking: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/fleet/summary',
  description: '排行表全部欄位直接來自 fleet/summary，跟 /vessels 頁是同一份資料，只是排序 UI 不同。',
  fields: [
    { ui: 'Speed Loss % / 趨勢 / 平均油耗 / 平均 RPM', source: 'latest_speed_loss_pct(或avg_speed_loss_pct) / speed_loss_trend / avg_consumption_mt / avg_rpm' },
    { ui: '距上次清洗 (天) / 超額成本 / 急迫度', source: 'days_since_hull_clean / excess_fuel_cost_usd_per_day / urgency' },
  ],
}

type SortKey = 'speedLossPct' | 'excessFuelCostUsdMtd' | 'urgency' | 'avgConsumptionMt' | 'daysSinceHullClean'
const sortKey = ref<SortKey>('speedLossPct')
const urgencyRank: Record<string, number> = { HIGH: 3, MEDIUM: 2, LOW: 1 }

const ranked = computed(() => {
  if (!vessels.value) return []
  return [...vessels.value].sort((a, b) => {
    if (sortKey.value === 'urgency') return urgencyRank[b.maintenanceUrgency] - urgencyRank[a.maintenanceUrgency]
    const aVal = (a as any)[sortKey.value] ?? 0
    const bVal = (b as any)[sortKey.value] ?? 0
    return bVal - aVal
  })
})

// Fetch speed-loss series for overlay chart
const seriesMap = ref<Record<string, SpeedLossSeries>>({})
const overlayLoading = ref(true)

watch(
  vessels,
  async (v) => {
    if (!v) return
    overlayLoading.value = true
    const ids = v.map((vv) => vv.imo)
    const results = await Promise.allSettled(ids.map((id) => fetchSpeedLossData(id)))
    results.forEach((r, i) => {
      if (r.status === 'fulfilled' && r.value) {
        seriesMap.value[ids[i]] = r.value
      }
    })
    overlayLoading.value = false
  },
  { immediate: true },
)

const overlayOption = computed(() => {
  if (!vessels.value) return {}
  const c = chart.value
  const colors = [
    c.brassAmber, c.fathomTeal, c.signalRed, c.inkSlate,
    '#8FA6B2', '#C8A84B', '#6B9E7F', '#A87B8C',
    '#5B8FBF', '#CF7B4B', '#7B8FBF', '#BF7B9E',
    '#5BAF8F', '#AF8F5B', '#8F5BAF',
  ]
  const series = vessels.value.map((v, i) => {
    const s = seriesMap.value[v.imo]
    const points = (s?.reports ?? []).slice(-180).map((r) => [r.day, r.speedLossPct])
    return {
      name: v.name,
      type: 'line' as const,
      showSymbol: false,
      lineStyle: { color: colors[i % colors.length], width: 1.5, opacity: 0.8 },
      data: points,
    }
  })
  return {
    animation: false,
    grid: { left: 56, right: 24, top: 40, bottom: 40 },
    legend: { top: 4, textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 10, color: c.inkSlate } },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
    },
    xAxis: {
      type: 'value',
      name: 'Day',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    yAxis: {
      type: 'value',
      name: 'Slip %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: '{value}%' },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series,
  }
})

function trendColor(trend: number | null): string {
  if (trend == null) return 'var(--color-ink-muted)'
  if (trend > 0.3) return 'var(--color-signal-red)'
  if (trend < -0.3) return 'var(--color-fathom-teal)'
  return 'var(--color-ink-muted)'
}
function trendArrow(trend: number | null): string {
  if (trend == null) return '—'
  if (trend > 0.3) return '↑'
  if (trend < -0.3) return '↓'
  return '→'
}

function goToVessel(imo: string) {
  router.push(`/vessels/${imo}/overview`)
}
</script>

<template>
  <div class="mx-auto max-w-[1440px] px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4">
    <div>
      <p class="panel-tag w-fit mb-2">FLEET-01</p>
      <h1 class="text-2xl">跨船隊分析</h1>
    </div>

    <StateDisplay v-if="state !== 'success'" :state="state === 'error' ? 'error' : 'loading'" />
    <template v-else>
      <!-- Speed Loss overlay chart -->
      <div class="panel p-3">
        <DataSourceTag :info="dsOverlay" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">
          全船隊 Speed Loss 趨勢疊圖（最近 180 筆 Noon Report calm condition）
        </p>
        <div class="h-[360px]">
          <StateDisplay v-if="overlayLoading" state="loading" />
          <VChart v-else :option="overlayOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <!-- Ranking table -->
      <div class="panel p-3">
        <DataSourceTag :info="dsRanking" />
        <div class="flex items-center justify-between mb-3">
          <label class="flex items-center gap-2 text-xs">
            <span class="text-[var(--color-ink-slate)]/60">排序依據</span>
            <select v-model="sortKey" class="border rounded-[2px] px-2 py-1 text-xs">
              <option value="speedLossPct">Speed Loss %</option>
              <option value="excessFuelCostUsdMtd">超額油耗成本</option>
              <option value="avgConsumptionMt">平均油耗</option>
              <option value="daysSinceHullClean">距上次清洗</option>
              <option value="urgency">維修急迫度</option>
            </select>
          </label>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm min-w-[860px]">
            <thead>
              <tr class="chart-divider">
                <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2 w-10">#</th>
                <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">船名</th>
                <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">船型</th>
                <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">Speed Loss %</th>
                <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">趨勢</th>
                <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">平均油耗 (MT/天)</th>
                <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">平均 RPM</th>
                <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">距上次清洗 (天)</th>
                <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">超額成本 (USD/天)</th>
                <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">急迫度</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(v, i) in ranked"
                :key="v.imo"
                class="chart-divider hover:bg-black/[0.02] cursor-pointer"
                @click="goToVessel(v.imo)"
              >
                <td class="px-3 py-2 font-data text-[var(--color-ink-muted)]">{{ i + 1 }}</td>
                <td class="px-3 py-2 font-display">{{ v.name }}</td>
                <td class="px-3 py-2 font-data text-xs text-[var(--color-ink-muted)]">{{ v.shipClass }}</td>
                <td class="px-3 py-2 font-data text-right">
                  <span
                    class="px-1.5 py-0.5 rounded-[3px] font-bold tabular-nums"
                    :style="{
                      color: v.speedLossPct >= 10 ? 'var(--color-signal-red)' : v.speedLossPct >= 6 ? 'var(--color-brass-amber)' : 'var(--color-fathom-teal)',
                      background: v.speedLossPct >= 10 ? 'color-mix(in srgb, var(--color-signal-red) 12%, transparent)' : v.speedLossPct >= 6 ? 'color-mix(in srgb, var(--color-brass-amber) 12%, transparent)' : 'color-mix(in srgb, var(--color-fathom-teal) 12%, transparent)',
                    }"
                  >{{ v.speedLossPct.toFixed(1) }}%</span>
                </td>
                <td class="px-3 py-2 font-data text-right tabular-nums">
                  <span :style="{ color: trendColor(v.speedLossTrend) }">
                    {{ trendArrow(v.speedLossTrend) }}
                    <template v-if="v.speedLossTrend != null">
                      {{ v.speedLossTrend > 0 ? '+' : '' }}{{ v.speedLossTrend.toFixed(2) }}
                    </template>
                  </span>
                </td>
                <td class="px-3 py-2 font-data text-right tabular-nums">
                  {{ v.avgConsumptionMt != null ? v.avgConsumptionMt.toFixed(1) : '—' }}
                </td>
                <td class="px-3 py-2 font-data text-right tabular-nums text-[var(--color-ink-muted)]">
                  {{ v.avgRpm != null ? v.avgRpm.toFixed(0) : '—' }}
                </td>
                <td
                  class="px-3 py-2 font-data text-right tabular-nums"
                  :class="v.daysSinceHullClean > 730 ? 'text-[var(--color-signal-red)]' : v.daysSinceHullClean > 365 ? 'text-[var(--color-brass-amber)]' : 'text-[var(--color-ink-muted)]'"
                >{{ v.daysSinceHullClean }}</td>
                <td class="px-3 py-2 font-data text-right tabular-nums text-[var(--color-signal-red)]">
                  {{ formatUsd(v.excessFuelCostUsdMtd) }}
                </td>
                <td class="px-3 py-2">
                  <span
                    class="font-semibold text-xs px-1.5 py-0.5 rounded-[3px]"
                    :style="{
                      color: URGENCY_COLOR[v.maintenanceUrgency],
                      background: `color-mix(in srgb, ${URGENCY_COLOR[v.maintenanceUrgency]} 14%, transparent)`,
                    }"
                  >{{ URGENCY_LABEL[v.maintenanceUrgency] }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
