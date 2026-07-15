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
    <!-- vessel spec card -->
    <div class="panel p-4">
      <DataSourceTag :info="dsSpec" />
      <PanelTag code="SPEC-01" class="mb-2" />
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 font-data text-sm">
        <div>
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">船型</p>
          <p>{{ vessel.shipClass }} · {{ vessel.type }}</p>
        </div>
        <div v-if="vessel.avgSpeedKn != null">
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">平均航速</p>
          <p>{{ vessel.avgSpeedKn.toFixed(1) }} kt</p>
        </div>
        <div>
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">航線</p>
          <p>{{ vessel.tradeRoute }}</p>
        </div>
        <div v-if="vessel.totalVoyages">
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">航次數</p>
          <p>{{ vessel.totalVoyages }} 次</p>
        </div>
        <div v-if="vessel.dataSpanDays">
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">資料期間</p>
          <p>{{ vessel.dataSpanDays }} 天</p>
        </div>
        <div v-if="vessel.totalRecords">
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">日報筆數</p>
          <p>{{ vessel.totalRecords.toLocaleString() }} 筆</p>
        </div>
      </div>
    </div>

    <!-- KPI cards row 1: speed loss + maintenance -->
    <div class="relative grid grid-cols-1 md:grid-cols-3 gap-3">
      <DataSourceTag :info="dsKpiRow1" />
      <div class="panel p-4 flex items-center gap-4">
        <FathometerGauge
          :value="Math.min(100, vessel.speedLossPct * 8)"
          :grade="vessel.foulingGrade"
          label="目前 SPEED LOSS"
          :display-value="`${vessel.speedLossPct.toFixed(1)}%`"
        />
        <div class="flex flex-col gap-1">
          <p class="font-data text-xs text-[var(--color-ink-slate)]/60">趨勢</p>
          <p
            class="font-data font-semibold"
            :style="{ color: trendColor(vessel.speedLossTrend) }"
          >
            <template v-if="vessel.speedLossTrend != null">
              {{ vessel.speedLossTrend > 0 ? '+' : '' }}{{ vessel.speedLossTrend.toFixed(2) }}%{{ trendArrow(vessel.speedLossTrend) }}
            </template>
            <template v-else>—</template>
          </p>
          <p class="font-data text-[10px] text-[var(--color-ink-slate)]/50">最新 vs 90天前</p>
        </div>
      </div>
      <KpiCard
        code="KPI-06"
        label="距上次水下清洗天數"
        :value="vessel.daysSinceHullClean"
        :formatter="(n) => `${Math.round(n)} 天`"
      />
      <KpiCard
        code="KPI-07"
        label="超額燃油成本 (USD/天)"
        :value="vessel.excessFuelCostUsdMtd"
        :formatter="formatUsd"
        tone="red"
      />
    </div>

    <!-- KPI cards row 2: performance averages -->
    <div class="relative grid grid-cols-2 md:grid-cols-4 gap-3">
      <DataSourceTag :info="dsKpiRow2" />
      <div class="panel p-3">
        <p class="font-display text-[10px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">平均油耗</p>
        <p class="font-data text-lg tabular-nums">
          {{ vessel.avgConsumptionMt != null ? vessel.avgConsumptionMt.toFixed(1) : '—' }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">MT/天</span>
        </p>
      </div>
      <div class="panel p-3">
        <p class="font-display text-[10px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">平均 RPM</p>
        <p class="font-data text-lg tabular-nums">
          {{ vessel.avgRpm != null ? vessel.avgRpm.toFixed(0) : '—' }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">RPM</span>
        </p>
      </div>
      <div class="panel p-3">
        <p class="font-display text-[10px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">距上次養護</p>
        <p class="font-data text-lg tabular-nums">
          {{ vessel.daysSinceMaintenance != null ? vessel.daysSinceMaintenance : '—' }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">天</span>
        </p>
      </div>
      <div class="panel p-3">
        <p class="font-display text-[10px] uppercase tracking-wide text-[var(--color-ink-slate)]/50 mb-1">距上次螺旋槳拋光</p>
        <p class="font-data text-lg tabular-nums">
          {{ vessel.daysSincePropPolish != null ? vessel.daysSincePropPolish : '—' }}
          <span class="text-xs text-[var(--color-ink-slate)]/60">天</span>
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
        <PanelTag code="MAP-02" />
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
      <!-- last maintenance events -->
      <div class="panel p-4">
        <DataSourceTag :info="dsMaint" />
        <PanelTag code="MAINT-01" class="mb-3" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">最近養護事件</p>
        <StateDisplay
          v-if="maintState !== 'success'"
          :state="maintState === 'error' ? 'error' : maintState === 'empty' ? 'empty' : 'loading'"
          empty-title="此船尚無養護事件記錄"
        />
        <ol v-else-if="maintData?.events.length" class="flex flex-col gap-3">
          <li
            v-for="evt in [...(maintData?.events ?? [])].sort((a, b) => b.event_day - a.event_day).slice(0, 6)"
            :key="`${evt.event_type}-${evt.event_day}`"
            class="flex items-center gap-3 text-sm"
          >
            <span class="status-dot bg-[var(--color-brass-amber)]" />
            <span class="font-data font-semibold">{{ evt.event_type }}</span>
            <span class="font-data text-[var(--color-ink-slate)]/60 text-xs ml-auto">
              Day {{ evt.event_day }}
            </span>
          </li>
        </ol>
        <p v-else class="text-sm text-[var(--color-ink-slate)]/50">尚無記錄</p>
      </div>

      <!-- quick links + last maintenance summary -->
      <div class="panel p-4">
        <PanelTag code="NAV-01" class="mb-3" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">快速連結</p>
        <div class="grid grid-cols-2 gap-2">
          <RouterLink
            v-for="link in quickLinks"
            :key="link.to"
            :to="link.to"
            class="border rounded-[2px] px-3 py-2 text-sm hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors duration-150 chart-divider"
          >
            {{ link.label }}
            <span
              v-if="dataSourceDebugEnabled && link.unreachable"
              class="ds-inline-badge"
              title="此路由未在 router/index.ts 註冊，目前點擊會被 catch-all 導回首頁"
            >⚪ UNREACHABLE</span>
          </RouterLink>
        </div>

        <div v-if="lastMaintEvent" class="mt-4 p-3 panel border rounded-[2px]">
          <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">最近一次養護</p>
          <div class="flex items-center gap-3">
            <FathometerGauge
              size="sm"
              :value="Math.min(100, vessel.speedLossPct * 8)"
              :grade="vessel.foulingGrade"
              :display-value="`${vessel.speedLossPct.toFixed(1)}%`"
            />
            <div class="text-sm">
              <p class="font-display">{{ lastMaintEvent.event_type }}</p>
              <p class="font-data text-xs text-[var(--color-ink-slate)]/60 mt-0.5">
                Day {{ lastMaintEvent.event_day }}
              </p>
              <p v-if="lastMaintEvent.hull_fouling_type" class="font-data text-xs text-[var(--color-ink-slate)]/60">
                污損: {{ lastMaintEvent.hull_fouling_type }}
              </p>
            </div>
          </div>
        </div>
      </div>
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
