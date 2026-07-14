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
import { formatUsd, STATUS_LABEL } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()

const { data: maintData, state: maintState } = useAsyncData(() => props.imo, getMaintenanceEvents)

const BASE_DATE = new Date('2020-01-01')
function dayToDate(day: number): string {
  const d = new Date(BASE_DATE)
  d.setDate(d.getDate() + Math.round(day))
  return d.toISOString().slice(0, 10)
}

// Last maintenance event for the overview widget
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
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- vessel spec card -->
    <div class="panel p-4">
      <PanelTag code="SPEC-01" class="mb-2" />
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 font-data text-sm">
        <div>
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">船型</p>
          <p>{{ vessel.type }}{{ vessel.teuCapacity ? ` · ${vessel.teuCapacity.toLocaleString()} TEU` : '' }}</p>
        </div>
        <div v-if="vessel.builtYear">
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">建造年</p>
          <p>{{ vessel.builtYear }}</p>
        </div>
        <div>
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">設計航速</p>
          <p>{{ vessel.designSpeedKt }} kt</p>
        </div>
        <div v-if="vessel.mainEngineModel">
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">主機型號</p>
          <p>{{ vessel.mainEngineModel }}</p>
        </div>
        <div>
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">航線</p>
          <p>{{ vessel.tradeRoute }}</p>
        </div>
      </div>
    </div>

    <!-- KPI cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
      <div class="panel p-4 flex items-center gap-4">
        <FathometerGauge
          :value="Math.min(100, vessel.speedLossPct * 8)"
          :grade="vessel.foulingGrade"
          label="目前 SPEED LOSS"
          :display-value="`${vessel.speedLossPct.toFixed(1)}%`"
        />
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
            <span class="font-data text-[var(--color-ink-slate)]/60 text-xs ml-auto">Day {{ evt.event_day }} · {{ dayToDate(evt.event_day) }}</span>
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
                Day {{ lastMaintEvent.event_day }} · {{ dayToDate(lastMaintEvent.event_day) }}
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
