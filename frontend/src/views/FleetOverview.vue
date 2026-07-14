<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { fetchKpis, fetchVessels } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import KpiCard from '@/components/KpiCard.vue'
import FleetMap from '@/components/FleetMap.vue'
import FathometerGauge from '@/components/FathometerGauge.vue'
import PanelTag from '@/components/PanelTag.vue'
import StateDisplay from '@/components/StateDisplay.vue'
import { formatUsd, STATUS_LABEL, URGENCY_LABEL, URGENCY_COLOR } from '@/utils/format'

const router = useRouter()

const { data: kpis, state: kpiState } = useAsyncData(() => true, fetchKpis, () => false)
const { data: vessels, state: vesselState } = useAsyncData(() => true, fetchVessels)

const priorityRanked = computed(() => {
  if (!vessels.value) return []
  return [...vessels.value].sort((a, b) => b.speedLossPct - a.speedLossPct).slice(0, 6)
})

function goToVessel(imo: string) {
  router.push(`/vessels/${imo}/overview`)
}
</script>

<template>
  <div class="mx-auto max-w-[1440px] px-4 md:px-6 py-4 md:py-6 flex flex-col gap-6">
    <div class="pt-1">
      <p class="eyebrow mb-1.5">OVR-01 · Fleet Command</p>
      <h1 class="text-[2rem] leading-none">船隊總覽 Dashboard</h1>
      <p class="font-mono text-xs text-[var(--color-ink-muted)] mt-2 tracking-[0.14em] uppercase">
        Fleet-wide continuous monitoring
      </p>
    </div>

    <!-- KPI row -->
    <section aria-label="船隊關鍵指標" class="grid grid-cols-2 md:grid-cols-3 gap-3">
      <template v-if="kpiState === 'success' && kpis">
        <KpiCard code="KPI-01" label="船隊總數" :value="kpis.totalVessels" />
        <KpiCard code="KPI-04" label="待安排維修船數" :value="kpis.pendingMaintenance" tone="amber" />
        <KpiCard
          code="KPI-05"
          label="船隊超額燃油成本 (USD/天)"
          :value="kpis.monthlyExcessFuelCostUsd"
          :formatter="formatUsd"
          tone="red"
        />
      </template>
      <div v-else class="col-span-5"><StateDisplay :state="kpiState === 'error' ? 'error' : 'loading'" /></div>
    </section>

    <!-- Map + priority ranking -->
    <section class="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-4">
      <div class="panel panel--accent-teal panel--map-glow p-3 flex flex-col gap-3">
        <div class="flex items-center justify-between pl-0.5">
          <PanelTag code="MAP-01" />
          <p class="map-glow-label font-display text-xs tracking-[0.08em] text-[var(--color-ink-muted)]">船隊即時位置</p>
        </div>
        <div class="map-glow-viewport rounded-[3px]">
          <div
            class="h-[460px] rounded-[3px] overflow-hidden border"
            style="border-color: color-mix(in srgb, var(--color-ink-slate) 16%, transparent)"
          >
            <FleetMap v-if="vessels" :vessels="vessels" @select="goToVessel" />
            <StateDisplay v-else :state="vesselState === 'error' ? 'error' : 'loading'" />
          </div>
        </div>
      </div>

      <div class="panel panel--accent-red p-4 flex flex-col gap-3">
        <div class="flex items-center justify-between pl-0.5">
          <PanelTag code="RANK-01" />
          <p class="font-display text-xs tracking-[0.08em] text-[var(--color-ink-muted)]">需優先處理</p>
        </div>
        <StateDisplay v-if="vesselState !== 'success'" :state="vesselState === 'error' ? 'error' : 'loading'" />
        <ul v-else class="flex flex-col gap-1.5">
          <li v-for="(v, i) in priorityRanked" :key="v.imo">
            <button
              class="w-full text-left flex items-center gap-3 rounded-[3px] px-2.5 py-2.5 border border-transparent transition-all duration-150 hover:bg-[var(--color-chart-paper-hi)] hover:border-[color-mix(in_srgb,var(--color-brass-amber)_40%,transparent)] group"
              @click="goToVessel(v.imo)"
            >
              <span class="font-mono text-[11px] text-[var(--color-ink-muted)] w-4 shrink-0 tabular-nums">{{ i + 1 }}</span>
              <FathometerGauge
                :value="Math.min(100, v.speedLossPct * 8)"
                :grade="v.foulingGrade"
                :display-value="`${v.speedLossPct.toFixed(1)}%`"
                size="sm"
              />
              <div class="flex-1 min-w-0">
                <p class="font-display text-sm truncate group-hover:text-[var(--color-brass-amber)] transition-colors">
                  {{ v.name }}
                </p>
                <p class="font-mono text-[11px] text-[var(--color-ink-muted)] mt-0.5">
                  {{ STATUS_LABEL[v.status] }} · 急迫度
                  <span :style="{ color: URGENCY_COLOR[v.maintenanceUrgency] }" class="font-semibold">{{
                    URGENCY_LABEL[v.maintenanceUrgency]
                  }}</span>
                </p>
              </div>
              <span class="text-[var(--color-ink-muted)] group-hover:text-[var(--color-brass-amber)] transition-colors" aria-hidden="true">›</span>
            </button>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>
