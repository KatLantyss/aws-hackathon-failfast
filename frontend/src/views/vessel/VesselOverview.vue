<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { VesselSummary } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import { getMaintenanceEvents } from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import { dataSourceDebugEnabled } from '@/composables/useDataSourceDebug'
import PanelTag from '@/components/PanelTag.vue'
import FathometerGauge from '@/components/FathometerGauge.vue'
import KpiCard from '@/components/KpiCard.vue'
import StateDisplay from '@/components/StateDisplay.vue'
import VesselFocusMap from '@/components/VesselFocusMap.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { formatUsd, STATUS_LABEL, URGENCY_COLOR, URGENCY_LABEL } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()

const { data: maintData, state: maintState } = useAsyncData(() => props.imo, getMaintenanceEvents)

const lastMaintEvent = computed(() => {
  if (!maintData.value?.events.length) return null
  return [...maintData.value.events].sort((a, b) => b.event_day - a.event_day)[0]
})

const quickLinks = computed(() => [
  { to: `/vessels/${props.imo}/noon-reports`, label: 'Noon Report', unreachable: false },
  { to: `/vessels/${props.imo}/speed-loss`, label: 'Speed Loss 分析', unreachable: false },
  { to: `/vessels/${props.imo}/fuel-attribution`, label: '速損歸因', unreachable: false },
  { to: `/vessels/${props.imo}/fuel-prediction`, label: '油耗預測', unreachable: false },
  { to: `/vessels/${props.imo}/maintenance-correlation`, label: '維修效能分析', unreachable: false },
])

const dsSpec: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/fleet/summary',
  description: '規格卡與下方兩排 KPI 皆來自同一組 vessel summary 資料（由 VesselLayout 往下傳的 vessel prop），全部是後端原始欄位。',
  fields: [
    { ui: '船型 / 航線', source: 'shipClass, type（tradeRoute 為前端依 W1/W2 船名列表寫死的固定字串）' },
    { ui: '平均航速 / 航次數 / 資料期間 / 日報筆數', source: 'avgSpeedKn / totalVoyages / dataSpanDays / totalRecords' },
  ],
}

const dsKpiRow1: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/fleet/summary',
  description: 'Speed Loss 量表、趨勢、距上次清洗天數、超額燃油成本皆為後端原始欄位。',
  fields: [
    { ui: '目前 Speed Loss 量表', source: 'speedLossPct（latest_speed_loss_pct）, foulingGrade（前端依 speedLossPct 門檻分級）' },
    { ui: '趨勢 (%／最新 vs 90天前)', source: 'speedLossTrend' },
    { ui: '距上次水下清洗天數', source: 'daysSinceHullClean' },
    { ui: '超額燃油成本 (USD/天)', source: 'excessFuelCostUsdMtd' },
  ],
}

const dsKpiRow2: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/fleet/summary',
  description: '平均油耗/RPM/SFOC/負載率/貨載、距上次養護/拋光天數、養護事件總數，皆為後端原始欄位，v-if 依欄位是否有值決定是否顯示。',
  fields: [
    { ui: '平均油耗 / 平均 RPM', source: 'avgConsumptionMt / avgRpm' },
    { ui: '距上次養護 / 距上次螺旋槳拋光', source: 'daysSinceMaintenance / daysSincePropPolish' },
    { ui: '平均 SFOC / 平均負載率 / 平均貨載', source: 'avgSfoc / avgLoadPct / avgCargoOnBoardMt' },
    { ui: '養護事件總數', source: 'totalMaintEvents' },
  ],
}

const dsMap: DataSourceInfo = {
  status: 'hybrid',
  endpoint: 'GET /api/v1/fleet/summary',
  description: '座標/航向/航速是 DynamoDB 真實欄位，但是歷史航行推算位置，不是即時 GPS 定位。',
  fields: [
    { ui: '目前位置座標', source: 'vessel.position.lat / lon', note: '歷史推算，非即時定位' },
    { ui: 'SPD / HDG', source: 'vessel.position.speedKt / headingDeg' },
    { ui: '目前港口 / 目的港', source: '無對應欄位，前端固定填 null，畫面上不顯示' },
  ],
}

const dsMaint: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/maintenance-events',
  description: '「最近養護事件」清單直接列出最新 6 筆，欄位原樣顯示，無前端加工。',
  fields: [
    { ui: '事件類型 / Day', source: 'event_type / event_day' },
    { ui: '污損類型（展開卡片內）', source: 'hull_fouling_type' },
  ],
}

function trendArrow(trend: number | null): string {
  if (trend == null) return ''
  if (trend > 0.3) return ' ↑'
  if (trend < -0.3) return ' ↓'
  return ' →'
}
function trendColor(trend: number | null): string {
  if (trend == null) return 'inherit'
  if (trend > 0.3) return 'var(--color-signal-red)'
  if (trend < -0.3) return 'var(--color-fathom-teal)'
  return 'var(--color-ink-muted)'
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- Speed Loss diagnostic: full width -->
    <div class="relative">
      <div class="panel p-4 flex items-center gap-6">
        <div class="shrink-0">
          <FathometerGauge
            :value="Math.min(100, vessel.speedLossPct * 8)"
            :grade="vessel.foulingGrade"
            :display-value="`${vessel.speedLossPct.toFixed(1)}%`"
            hide-grade-badge
          />
        </div>
        <div class="flex flex-col gap-2">
          <p class="font-data text-xs text-[var(--color-ink-slate)]/60 mb-1">趨勢（90天 vs 全期）</p>
          <p
            class="font-data font-semibold text-lg"
            :style="{ color: trendColor(vessel.speedLossTrend) }"
          >
            <template v-if="vessel.speedLossTrend != null">
              {{ vessel.speedLossTrend > 0 ? '+' : '' }}{{ vessel.speedLossTrend.toFixed(2) }}% {{ trendArrow(vessel.speedLossTrend) }}
            </template>
            <template v-else>—</template>
          </p>
        </div>
      </div>
    </div>

    <!-- Action row: 4 KPI cards -->
    <div class="relative grid grid-cols-2 md:grid-cols-4 gap-3">
      <KpiCard
        label="距清洗"
        :value="vessel.daysSinceHullClean"
        :formatter="(n) => `${Math.round(n)}d`"
      />
      <KpiCard
        label="急迫度"
        :value="vessel.maintenanceUrgency"
        :formatter="(v) => URGENCY_LABEL[v]"
        :tone="vessel.maintenanceUrgency === 'HIGH' ? 'red' : vessel.maintenanceUrgency === 'MEDIUM' ? 'amber' : 'green'"
      />
      <KpiCard
        label="超額成本"
        :value="vessel.excessFuelCostUsdMtd"
        :formatter="formatUsd"
        tone="red"
      />
      <KpiCard
        label="平均油耗"
        :value="vessel.avgConsumptionMt"
        :formatter="(n) => n ? `${n.toFixed(1)}MT` : '—'"
      />
    </div>

    <!-- Reference info: 1 row -->
    <div class="relative grid grid-cols-2 lg:grid-cols-5 gap-3">
      <div class="panel p-3">
        <p class="font-display text-[9px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">SFOC</p>
        <p class="font-data text-base font-semibold">
          {{ vessel.avgSfoc ? vessel.avgSfoc.toFixed(0) : '—' }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">g/kWh</span>
        </p>
      </div>
      <div class="panel p-3">
        <p class="font-display text-[9px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">負載率</p>
        <p class="font-data text-base font-semibold">
          {{ vessel.avgLoadPct ? vessel.avgLoadPct.toFixed(1) : '—' }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">% MCR</span>
        </p>
      </div>
      <div class="panel p-3">
        <p class="font-display text-[9px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">平均貨載</p>
        <p class="font-data text-base font-semibold">
          {{ vessel.avgCargoOnBoardMt ? (vessel.avgCargoOnBoardMt / 1000).toFixed(0) : '—' }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">k MT</span>
        </p>
      </div>
      <div class="panel p-3">
        <p class="font-display text-[9px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">養護事件</p>
        <p class="font-data text-base font-semibold">
          {{ vessel.totalMaintEvents != null ? vessel.totalMaintEvents : '—' }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">次</span>
        </p>
      </div>
      <div class="panel p-3">
        <p class="font-display text-[9px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">平均 RPM</p>
        <p class="font-data text-base font-semibold">
          {{ vessel.avgRpm ? vessel.avgRpm.toFixed(0) : '—' }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">rpm</span>
        </p>
      </div>
    </div>

    <!-- focused position map -->
    <div class="panel panel--map-glow p-3 flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <p class="map-glow-label font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70">目前位置</p>
      </div>
      <div class="map-glow-viewport rounded-[2px]">
        <div
          class="h-[320px] rounded-[2px] overflow-hidden border"
          style="border-color: color-mix(in srgb, var(--color-ink-slate) 18%, transparent)"
        >
          <VesselFocusMap :vessel="vessel" />
        </div>
      </div>
      <p class="map-glow-label font-data text-xs text-[var(--color-ink-slate)]/60 px-1">
        {{ STATUS_LABEL[vessel.status] }}{{ vessel.currentPort ? ' · ' + vessel.currentPort : '' }} · SPD
        {{ vessel.position.speedKt.toFixed(1) }} kt · HDG {{ vessel.position.headingDeg }}° · {{
          vessel.position.lat.toFixed(2)
        }}, {{ vessel.position.lon.toFixed(2) }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.ds-inline-badge {
  display: inline-block;
  margin-left: 6px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--color-signal-red) 16%, transparent);
  color: var(--color-signal-red);
  vertical-align: middle;
}
</style>
