<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { VesselSummary } from '@/types/fleet'
import { getMaintenanceEvents } from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import PanelTag from '@/components/PanelTag.vue'
import FathometerGauge from '@/components/FathometerGauge.vue'
import KpiCard from '@/components/KpiCard.vue'
import StateDisplay from '@/components/StateDisplay.vue'
import VesselFocusMap from '@/components/VesselFocusMap.vue'
import { formatUsd, STATUS_LABEL, URGENCY_LABEL, URGENCY_COLOR } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()

const { data: maintData, state: maintState } = useAsyncData(() => props.imo, getMaintenanceEvents)

const lastMaintEvent = computed(() => {
  if (!maintData.value?.events.length) return null
  return [...maintData.value.events].sort((a, b) => b.event_day - a.event_day)[0]
})

const quickLinks = computed(() => [
  { to: `/vessels/${props.imo}/noon-reports`, label: 'Noon Report' },
  { to: `/vessels/${props.imo}/speed-loss`, label: 'Speed Loss 分析' },
  { to: `/vessels/${props.imo}/fuel-attribution`, label: '速損歸因' },
  { to: `/vessels/${props.imo}/maintenance-correlation`, label: '維修效能分析' },
  { to: `/vessels/${props.imo}/maintenance-advisor`, label: '維修建議' },
])

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
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
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
            :style="{ color: trendColor(vessel.slipTrend) }"
          >
            <template v-if="vessel.slipTrend != null">
              {{ vessel.slipTrend > 0 ? '+' : '' }}{{ vessel.slipTrend.toFixed(2) }}%{{ trendArrow(vessel.slipTrend) }}
            </template>
            <template v-else>—</template>
          </p>
          <p class="font-data text-[10px] text-[var(--color-ink-slate)]/50">近90天 vs 全期</p>
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
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
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

    <!-- urgency badge -->
    <div class="flex items-center gap-3 px-1">
      <span class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/60">維修急迫度</span>
      <span
        class="font-semibold text-sm px-2.5 py-0.5 rounded-[3px]"
        :style="{
          color: URGENCY_COLOR[vessel.maintenanceUrgency],
          background: `color-mix(in srgb, ${URGENCY_COLOR[vessel.maintenanceUrgency]} 14%, transparent)`,
        }"
      >{{ URGENCY_LABEL[vessel.maintenanceUrgency] }}</span>
      <span v-if="vessel.lastHullCleanType" class="font-data text-xs text-[var(--color-ink-slate)]/50">
        上次清洗：{{ vessel.lastHullCleanType }}
      </span>
      <span v-if="vessel.lastEventType" class="font-data text-xs text-[var(--color-ink-slate)]/50">
        · 最後養護：{{ vessel.lastEventType }}
      </span>
    </div>

    <!-- focused position map -->
    <div class="panel panel--map-glow p-3 flex flex-col gap-2">
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
