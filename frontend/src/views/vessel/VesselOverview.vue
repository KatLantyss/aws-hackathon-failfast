<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { VesselSummary } from '@/types/fleet'
import { fetchInspections } from '@/mock/api'
import { useAsyncData } from '@/composables/useAsyncData'
import PanelTag from '@/components/PanelTag.vue'
import FathometerGauge from '@/components/FathometerGauge.vue'
import KpiCard from '@/components/KpiCard.vue'
import StateDisplay from '@/components/StateDisplay.vue'
import VesselFocusMap from '@/components/VesselFocusMap.vue'
import { formatDate, formatUsd, STATUS_LABEL } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()

const { data: inspections, state: inspectionState } = useAsyncData(() => props.imo, fetchInspections)

const recentPortCalls = computed(() => {
  // Mock recent port calls derived from trade route; illustrative only.
  const ports = ['Kaohsiung', 'Singapore', 'Colombo', 'Rotterdam', 'Ningbo', 'Fujairah', 'Hamburg']
  return ports.slice(0, 6).map((port, i) => ({
    port,
    date: new Date(Date.now() - i * 9 * 86400000).toISOString().slice(0, 10),
  }))
})

const quickLinks = computed(() => [
  { to: `/vessels/${props.imo}/noon-reports`, label: 'Noon Report' },
  { to: `/vessels/${props.imo}/inspections`, label: '水下檢查報告' },
  { to: `/vessels/${props.imo}/speed-loss`, label: 'Speed Loss 分析' },
  { to: `/vessels/${props.imo}/fuel-attribution`, label: '油耗歸因' },
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
          <p>{{ vessel.type }} · {{ vessel.teuCapacity.toLocaleString() }} TEU</p>
        </div>
        <div>
          <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">建造年</p>
          <p>{{ vessel.builtYear }}</p>
        </div>
        <div>
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
        label="本季累積超額油耗成本"
        :value="vessel.excessFuelCostUsdMtd * 3"
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
      <!-- port call timeline -->
      <div class="panel p-4">
        <PanelTag code="PORT-01" class="mb-3" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">最近港口停靠時間軸</p>
        <ol class="flex flex-col gap-3">
          <li v-for="call in recentPortCalls" :key="call.port + call.date" class="flex items-center gap-3 text-sm">
            <span class="status-dot bg-[var(--color-brass-amber)]" />
            <span class="font-display">{{ call.port }}</span>
            <span class="font-data text-[var(--color-ink-slate)]/60 text-xs ml-auto">{{ formatDate(call.date) }}</span>
          </li>
        </ol>
      </div>

      <!-- quick links -->
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

        <div class="mt-4">
          <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">最近一次水下檢查</p>
          <StateDisplay
            v-if="inspectionState !== 'success'"
            :state="inspectionState === 'error' ? 'error' : inspectionState === 'empty' ? 'empty' : 'loading'"
            empty-title="此船尚無水下檢查記錄"
            empty-hint="前往水下檢查頁面新增第一筆紀錄。"
          />
          <div v-else-if="inspections && inspections.length" class="flex items-center gap-3">
            <FathometerGauge
              size="sm"
              :value="inspections[0].biofoulingScore"
              :grade="inspections[0].foulingGrade"
              :display-value="`${inspections[0].biofoulingScore}`"
            />
            <div class="text-sm">
              <p>{{ formatDate(inspections[0].date) }} · {{ inspections[0].port }}</p>
              <p class="text-xs text-[var(--color-ink-slate)]/60">{{ inspections[0].surveyor }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
