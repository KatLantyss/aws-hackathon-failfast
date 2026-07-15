<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { fetchKpis, fetchVessels } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import KpiCard from '@/components/KpiCard.vue'
import FleetMap from '@/components/FleetMap.vue'
import PanelTag from '@/components/PanelTag.vue'
import StateDisplay from '@/components/StateDisplay.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import type { DataSourceInfo } from '@/types/dataSource'
import { formatUsd, URGENCY_LABEL, URGENCY_COLOR } from '@/utils/format'

const router = useRouter()

const { data: kpis, state: kpiState } = useAsyncData(() => true, fetchKpis, () => false)
const { data: vessels, state: vesselState } = useAsyncData(() => true, fetchVessels)

const dsKpi: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/fleet/summary',
  description: '3 張 KPI 卡直接取自 fleet/summary 彙總欄位，無前端加工。',
  fields: [
    { ui: '船隊總數', source: 'total_vessels' },
    { ui: '待安排維修船數', source: 'pending_maintenance' },
    { ui: '船隊超額燃油成本 (USD/天)', source: 'total_excess_fuel_cost_usd_per_day' },
  ],
}

const dsMap: DataSourceInfo = {
  status: 'hybrid',
  endpoint: 'GET /api/v1/fleet/summary',
  description: '座標/航向/航速是 DynamoDB 真實欄位，但本質是歷史 Noon Report 推算位置，不是即時 AIS 定位——標題「即時位置」用語與實際資料性質有落差。',
  fields: [
    { ui: '船舶座標', source: 'per_vessel[].lat / lon', note: '歷史航行推算，非即時 GPS' },
    { ui: '船艏朝向', source: 'per_vessel[].heading_deg' },
    { ui: '航速圖示', source: 'per_vessel[].speed_kt' },
    { ui: '污損量表 / 顏色', source: 'speedLossPct → foulingGrade（前端門檻分級：<3 Clean / <7 Light / <13 Moderate / 其餘 Heavy）' },
  ],
}

const dsRanking: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/fleet/summary',
  description: '取 per_vessel 依 speedLossPct 由前端排序後顯示前 6 艘，數值本身皆為後端原始欄位。',
  fields: [
    { ui: 'Speed Loss % 進度條 / 數值', source: 'latest_speed_loss_pct（或 avg_speed_loss_pct）' },
    { ui: '急迫度標籤', source: 'urgency' },
    { ui: '建議動作（UWC/PP/UWC+PP）', source: 'recommended_action' },
    { ui: '距上次船殼清洗天數', source: 'days_since_hull_clean' },
    { ui: 'DD 到期', source: 'dd_due' },
    { ui: '超額燃油成本 (USD/天)', source: 'excess_fuel_cost_usd_per_day' },
  ],
}

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
      <h1 class="text-[2rem] leading-none">船隊總覽 Dashboard</h1>
      <p class="font-mono text-xs text-[var(--color-ink-muted)] mt-2 tracking-[0.14em] uppercase">
        Fleet-wide continuous monitoring
      </p>
    </div>

    <!-- KPI row -->
    <section aria-label="船隊關鍵指標" class="relative grid grid-cols-2 md:grid-cols-3 gap-3">
      <DataSourceTag :info="dsKpi" />
      <template v-if="kpiState === 'success' && kpis">
        <KpiCard label="船隊總數" :value="kpis.totalVessels" />
        <KpiCard label="待安排維修船數" :value="kpis.pendingMaintenance" tone="amber" />
        <KpiCard
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
        <DataSourceTag :info="dsMap" />
        <div class="flex items-center justify-between pl-0.5">
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
        <DataSourceTag :info="dsRanking" />
        <div class="flex items-center justify-between pl-0.5">
          <p class="font-display text-xs tracking-[0.08em] text-[var(--color-ink-muted)]">需優先處理</p>
          <span class="font-mono text-[10px] text-[var(--color-ink-muted)]">依 Speed Loss % 排序</span>
        </div>
        <StateDisplay v-if="vesselState !== 'success'" :state="vesselState === 'error' ? 'error' : 'loading'" />
        <ul v-else class="flex flex-col gap-1.5">
          <li v-for="(v, i) in priorityRanked" :key="v.imo">
            <button
              class="w-full text-left flex flex-col gap-1.5 rounded-[3px] px-2.5 py-2.5 border border-transparent transition-all duration-150 hover:bg-[var(--color-chart-paper-hi)] hover:border-[color-mix(in_srgb,var(--color-brass-amber)_40%,transparent)] group"
              @click="goToVessel(v.imo)"
            >
              <!-- 第一行：排名 + 船名 + 急迫度 + 箭頭 -->
              <div class="flex items-center gap-2">
                <span class="font-mono text-[11px] text-[var(--color-ink-muted)] w-4 shrink-0 tabular-nums">{{ i + 1 }}</span>
                <span class="font-display text-sm flex-1 truncate group-hover:text-[var(--color-brass-amber)] transition-colors">
                  {{ v.name }}
                </span>
                <span
                  class="font-display text-[10px] px-1.5 py-0.5 rounded-[2px] shrink-0"
                  :style="{
                    color: URGENCY_COLOR[v.maintenanceUrgency],
                    background: `color-mix(in srgb, ${URGENCY_COLOR[v.maintenanceUrgency]} 14%, transparent)`,
                  }"
                >{{ URGENCY_LABEL[v.maintenanceUrgency] }}</span>
                <span class="text-[var(--color-ink-muted)] group-hover:text-[var(--color-brass-amber)] transition-colors shrink-0" aria-hidden="true">›</span>
              </div>

              <!-- 第二行：Speed Loss 進度條 + 數值 -->
              <div class="flex items-center gap-2 pl-6">
                <div class="flex-1 h-1.5 rounded-full bg-[var(--color-ink-slate)]/10 overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all"
                    :style="{
                      width: `${Math.min(100, v.speedLossPct * 6)}%`,
                      background: v.foulingGrade === 'Heavy' ? 'var(--color-signal-red)'
                        : v.foulingGrade === 'Moderate' ? 'var(--color-brass-amber)'
                        : 'var(--color-fathom-teal)',
                    }"
                  />
                </div>
                <span class="font-data text-xs tabular-nums shrink-0"
                  :style="{
                    color: v.foulingGrade === 'Heavy' ? 'var(--color-signal-red)'
                      : v.foulingGrade === 'Moderate' ? 'var(--color-brass-amber)'
                      : 'var(--color-fathom-teal)',
                  }"
                >{{ v.speedLossPct.toFixed(1) }}%</span>
                <span class="font-mono text-[10px] text-[var(--color-ink-muted)] shrink-0">SL</span>
              </div>

              <!-- 第三行：維修相關資訊 -->
              <div class="flex items-center gap-3 pl-6 flex-wrap">
                <!-- 建議動作 -->
                <span v-if="v.recommendedAction" class="font-display text-[10px] px-1.5 py-0.5 rounded-[2px] bg-[var(--color-signal-red)]/10 text-[var(--color-signal-red)]">
                  建議：{{ v.recommendedAction }}
                </span>
                <!-- 距上次船殼清洗 -->
                <span class="font-mono text-[10px] text-[var(--color-ink-muted)]">
                  距清洗 <strong class="font-data text-[var(--color-ink-slate)]">{{ v.daysSinceHullClean }}</strong> 天
                </span>
                <!-- DD 到期 -->
                <span v-if="v.ddDue" class="font-display text-[10px] px-1.5 py-0.5 rounded-[2px] bg-[var(--color-brass-amber)]/10 text-[var(--color-brass-amber)]">
                  DD 到期
                </span>
                <!-- 超額油耗成本 -->
                <span v-if="v.excessFuelCostUsdMtd > 0" class="font-mono text-[10px] text-[var(--color-ink-muted)]">
                  超額 <strong class="font-data text-[var(--color-signal-red)]">{{ formatUsd(v.excessFuelCostUsdMtd) }}</strong>/天
                </span>
              </div>
            </button>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>
