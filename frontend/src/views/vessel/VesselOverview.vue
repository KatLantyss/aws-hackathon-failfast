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
import { formatUsd, STATUS_LABEL } from '@/utils/format'

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
    { ui: '目前 Speed Loss 量表', source: 'speedLossPct（recent_90d_slip_pct）, foulingGrade（前端依 speedLossPct 門檻分級）' },
    { ui: '趨勢 (%／近90天 vs 全期)', source: 'slipTrend' },
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
    <!-- Basic info + Main diagnostic: Speed Loss (side-by-side) -->
    <div class="relative grid grid-cols-1 md:grid-cols-[200px_1fr] gap-3">
      <DataSourceTag :info="dsKpiRow1" />

      <!-- Left: Basic info cards -->
      <div class="flex flex-col gap-2">
        <div class="px-3 py-2 rounded-[3px] bg-[var(--color-ink-slate)]/5 text-xs font-data">
          <span class="text-[var(--color-ink-slate)]/60">船型：</span>
          <span>{{ vessel.shipClass }}</span>
        </div>
        <div v-if="vessel.dataSpanDays" class="px-3 py-2 rounded-[3px] bg-[var(--color-ink-slate)]/5 text-xs font-data">
          <span class="text-[var(--color-ink-slate)]/60">資料期間：</span>
          <span>{{ vessel.dataSpanDays }} 天</span>
        </div>
        <div v-if="vessel.totalRecords" class="px-3 py-2 rounded-[3px] bg-[var(--color-ink-slate)]/5 text-xs font-data">
          <span class="text-[var(--color-ink-slate)]/60">日報筆數：</span>
          <span>{{ vessel.totalRecords.toLocaleString() }} 筆</span>
        </div>
      </div>

      <!-- Right: Speed Loss diagnostic -->
      <div class="panel p-4 flex items-center gap-6">
        <FathometerGauge
          :value="Math.min(100, vessel.speedLossPct * 8)"
          :grade="vessel.foulingGrade"
          label="船體污損程度"
          :display-value="`${vessel.speedLossPct.toFixed(1)}%`"
        />
        <div class="flex flex-col gap-2">
          <div>
            <p class="font-data text-xs text-[var(--color-ink-slate)]/60 mb-1">趨勢（90天 vs 全期）</p>
            <p
              class="font-data font-semibold text-lg"
              :style="{ color: trendColor(vessel.slipTrend) }"
            >
              <template v-if="vessel.slipTrend != null">
                {{ vessel.slipTrend > 0 ? '+' : '' }}{{ vessel.slipTrend.toFixed(2) }}% {{ trendArrow(vessel.slipTrend) }}
              </template>
              <template v-else>—</template>
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Action row: 4 columns -->
    <div class="relative grid grid-cols-2 md:grid-cols-4 gap-3">
      <DataSourceTag :info="dsKpiRow1" />
      <KpiCard
        label="距上次水下清洗天數"
        :value="vessel.daysSinceHullClean"
        :formatter="(n) => `${Math.round(n)} 天`"
      />
      <KpiCard
        label="維修急迫度"
        :value="vessel.maintenanceUrgency"
        :formatter="(v) => URGENCY_LABEL[v]"
        :tone="vessel.maintenanceUrgency === 'HIGH' ? 'red' : vessel.maintenanceUrgency === 'MEDIUM' ? 'amber' : 'green'"
      />
      <KpiCard
        label="趨勢"
        :value="vessel.slipTrend"
        :formatter="(v) => v != null ? `${v > 0 ? '+' : ''}${v.toFixed(2)}% ${trendArrow(v)}` : '—'"
      />
      <KpiCard
        label="超額燃油成本 (USD/天)"
        :value="vessel.excessFuelCostUsdMtd"
        :formatter="formatUsd"
        tone="red"
      />
    </div>

    <!-- Reference info: performance averages -->
    <div class="relative grid grid-cols-2 md:grid-cols-4 gap-3">
      <DataSourceTag :info="dsKpiRow2" />
      <div class="panel p-3">
        <p class="font-display text-[10px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">平均油耗</p>
        <p class="font-data text-lg tabular-nums">
          {{ vessel.avgConsumptionMt != null ? vessel.avgConsumptionMt.toFixed(1) : '—' }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">MT/天</span>
        </p>
      </div>
      <div class="panel p-3" v-if="vessel.avgSfoc">
        <p class="font-display text-[10px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">平均 SFOC</p>
        <p class="font-data text-lg tabular-nums">
          {{ vessel.avgSfoc.toFixed(0) }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">g/kWh</span>
        </p>
      </div>
      <div class="panel p-3" v-if="vessel.avgLoadPct">
        <p class="font-display text-[10px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">平均負載率</p>
        <p class="font-data text-lg tabular-nums">
          {{ vessel.avgLoadPct.toFixed(1) }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">% MCR</span>
        </p>
      </div>
      <div class="panel p-3" v-if="vessel.avgCargoOnBoardMt">
        <p class="font-display text-[10px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">平均貨載</p>
        <p class="font-data text-lg tabular-nums">
          {{ (vessel.avgCargoOnBoardMt / 1000).toFixed(0) }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">k MT</span>
        </p>
      </div>
      <div class="panel p-3" v-if="vessel.totalMaintEvents != null">
        <p class="font-display text-[10px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">養護事件總數</p>
        <p class="font-data text-lg tabular-nums">
          {{ vessel.totalMaintEvents }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">次</span>
        </p>
      </div>
    </div>

    <!-- focused position map -->
    <div class="panel panel--map-glow p-3 flex flex-col gap-2">
      <DataSourceTag :info="dsMap" />
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

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
