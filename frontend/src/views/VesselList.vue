<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  FlexRender,
  getCoreRowModel,
  getSortedRowModel,
  useVueTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/vue-table'
import { fetchVessels } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import FathometerGauge from '@/components/FathometerGauge.vue'
import type { VesselSummary } from '@/types/fleet'
import { speedLossColor, URGENCY_LABEL, URGENCY_COLOR, formatUsd } from '@/utils/format'

const router = useRouter()
const { data: vessels, state } = useAsyncData(() => true, fetchVessels)

const typeFilter = ref('all')
const keyword = ref('')
const expandedImo = ref<string | null>(null)
const sorting = ref<SortingState>([])

const vesselTypes = computed(() => {
  if (!vessels.value) return []
  return Array.from(new Set(vessels.value.map((v) => v.shipClass)))
})

const filtered = computed<VesselSummary[]>(() => {
  if (!vessels.value) return []
  return vessels.value.filter((v) => {
    if (typeFilter.value !== 'all' && v.shipClass !== typeFilter.value) return false
    if (keyword.value && !`${v.name} ${v.imo}`.toLowerCase().includes(keyword.value.toLowerCase())) return false
    return true
  })
})

const columns: ColumnDef<VesselSummary>[] = [
  { accessorKey: 'name',          header: '船舶代號', enableSorting: true },
  { accessorKey: 'shipClass',     header: '船型',     enableSorting: true },
  { accessorKey: 'speedLossPct',  header: 'Speed Loss %', enableSorting: true },
  { id: 'avgConsumption',         header: '平均油耗 (MT/天)', accessorFn: (r) => r.avgConsumptionMt, enableSorting: true },
  { id: 'avgRpm',                 header: '平均 RPM',  accessorFn: (r) => r.avgRpm, enableSorting: true },
  { id: 'daysSinceHullClean',     header: '距上次清洗 (天)', accessorFn: (r) => r.daysSinceHullClean, enableSorting: true },
  { id: 'daysSincePropPolish',    header: '距上次螺旋槳拋光 (天)', accessorFn: (r) => r.daysSincePropPolish, enableSorting: true },
  { id: 'excessCost',             header: '超額油耗成本 (USD/天)', accessorFn: (r) => r.excessFuelCostUsdMtd, enableSorting: true },
  { id: 'urgency',                header: '維修急迫度', accessorFn: (r) => r.maintenanceUrgency, enableSorting: true },
]

const table = useVueTable({
  get data() { return filtered.value },
  columns,
  state: {
    get sorting() { return sorting.value },
  },
  onSortingChange: (updaterOrValue) => {
    sorting.value = typeof updaterOrValue === 'function' ? updaterOrValue(sorting.value) : updaterOrValue
  },
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
})

function toggleExpand(imo: string) {
  expandedImo.value = expandedImo.value === imo ? null : imo
}

function goToVessel(imo: string) {
  router.push(`/vessels/${imo}/overview`)
}

function trendArrow(trend: number | null): string {
  if (trend == null) return '—'
  if (trend > 0.5) return '↑'   // degrading
  if (trend < -0.5) return '↓'  // improving
  return '→'
}
function trendColor(trend: number | null): string {
  if (trend == null) return 'var(--color-ink-muted)'
  if (trend > 0.5) return 'var(--color-signal-red)'
  if (trend < -0.5) return 'var(--color-fathom-teal)'
  return 'var(--color-ink-muted)'
}
</script>

<template>
  <div class="mx-auto max-w-[1440px] px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4">
    <div class="flex items-center justify-between">
      <div>
        <p class="eyebrow mb-1.5">LIST-01 · Fleet Register</p>
        <h1 class="text-[1.9rem] leading-none">船隊列表</h1>
      </div>
    </div>

    <!-- Filters -->
    <div class="panel p-3.5 flex flex-wrap items-center gap-4">
      <label class="flex items-center gap-2 text-sm">
        <span class="col-head">船型</span>
        <select v-model="typeFilter" class="field">
          <option value="all">全部</option>
          <option v-for="t in vesselTypes" :key="t" :value="t">{{ t }}</option>
        </select>
      </label>
      <label class="flex items-center gap-2 text-sm flex-1 min-w-[200px]">
        <span class="col-head">關鍵字</span>
        <input v-model="keyword" type="search" placeholder="船舶代號" class="field flex-1" />
      </label>
    </div>

    <StateDisplay v-if="state !== 'success'" :state="state === 'error' ? 'error' : 'loading'" />

    <div v-else class="panel panel--accent overflow-x-auto">
      <table class="w-full text-sm min-w-[900px]">
        <thead>
          <tr
            v-for="hg in table.getHeaderGroups()"
            :key="hg.id"
            class="border-b-2"
            style="border-color: color-mix(in srgb, var(--color-ink-slate) 22%, transparent)"
          >
            <th class="w-8"></th>
            <th
              v-for="h in hg.headers"
              :key="h.id"
              class="col-head text-left px-3 py-3 cursor-pointer select-none whitespace-nowrap hover:text-[var(--color-ink-slate)] transition-colors"
              @click="h.column.getToggleSortingHandler()?.($event)"
            >
              <FlexRender :render="h.column.columnDef.header" :props="h.getContext()" />
              <span v-if="h.column.getIsSorted() === 'asc'"> ▲</span>
              <span v-else-if="h.column.getIsSorted() === 'desc'"> ▼</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in table.getRowModel().rows" :key="row.id">
            <tr
              class="chart-divider cursor-pointer transition-colors hover:bg-[var(--color-chart-paper-hi)]"
              @click="goToVessel(row.original.imo)"
            >
              <!-- expand toggle -->
              <td class="px-2 py-2 text-center">
                <button
                  class="text-[var(--color-ink-slate)]/60 hover:text-[var(--color-ink-slate)]"
                  aria-label="展開詳情"
                  @click.stop="toggleExpand(row.original.imo)"
                >{{ expandedImo === row.original.imo ? '▾' : '▸' }}</button>
              </td>

              <!-- 船舶代號 -->
              <td class="px-3 py-3 font-display text-[15px] tracking-wide">{{ row.original.name }}</td>

              <!-- 船型 -->
              <td class="px-3 py-3 font-data text-xs text-[var(--color-ink-muted)]">{{ row.original.shipClass }}</td>

              <!-- Speed Loss -->
              <td class="px-3 py-3">
                <div class="flex items-center gap-1.5">
                  <span
                    class="font-data font-bold tabular-nums px-1.5 py-0.5 rounded-[3px]"
                    :style="{
                      color: speedLossColor(row.original.speedLossPct),
                      background: `color-mix(in srgb, ${speedLossColor(row.original.speedLossPct)} 12%, transparent)`,
                    }"
                  >{{ row.original.speedLossPct.toFixed(1) }}%</span>
                  <span
                    class="font-data text-xs"
                    :style="{ color: trendColor(row.original.slipTrend) }"
                    :title="`Trend: ${row.original.slipTrend != null ? row.original.slipTrend.toFixed(2) : '—'}%`"
                  >{{ trendArrow(row.original.slipTrend) }}</span>
                </div>
              </td>

              <!-- 平均油耗 -->
              <td class="px-3 py-3 font-data text-right tabular-nums">
                {{ row.original.avgConsumptionMt != null ? row.original.avgConsumptionMt.toFixed(1) : '—' }}
              </td>

              <!-- 平均 RPM -->
              <td class="px-3 py-3 font-data text-right tabular-nums text-[var(--color-ink-muted)]">
                {{ row.original.avgRpm != null ? row.original.avgRpm.toFixed(0) : '—' }}
              </td>

              <!-- 距上次清洗 -->
              <td class="px-3 py-3 font-data text-right tabular-nums"
                :class="row.original.daysSinceHullClean > 730 ? 'text-[var(--color-signal-red)]' : row.original.daysSinceHullClean > 365 ? 'text-[var(--color-brass-amber)]' : 'text-[var(--color-ink-muted)]'"
              >{{ row.original.daysSinceHullClean }}</td>

              <!-- 距上次螺旋槳拋光 -->
              <td class="px-3 py-3 font-data text-right tabular-nums text-[var(--color-ink-muted)]">
                {{ row.original.daysSincePropPolish ?? '—' }}
              </td>

              <!-- 超額成本 -->
              <td class="px-3 py-3 font-data text-right tabular-nums text-[var(--color-signal-red)]">
                {{ formatUsd(row.original.excessFuelCostUsdMtd) }}
              </td>

              <!-- 急迫度 -->
              <td class="px-3 py-3">
                <span
                  class="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-[3px]"
                  :style="{
                    color: URGENCY_COLOR[row.original.maintenanceUrgency],
                    background: `color-mix(in srgb, ${URGENCY_COLOR[row.original.maintenanceUrgency]} 14%, transparent)`,
                  }"
                >{{ URGENCY_LABEL[row.original.maintenanceUrgency] }}</span>
              </td>
            </tr>

            <!-- expanded detail row -->
            <tr v-if="expandedImo === row.original.imo" class="chart-divider bg-black/[0.015]">
              <td colspan="10" class="px-6 py-4">
                <div class="grid grid-cols-1 md:grid-cols-[auto_1fr] gap-6 items-start">
                  <FathometerGauge
                    :value="Math.min(100, row.original.speedLossPct * 8)"
                    :grade="row.original.foulingGrade"
                    label="Speed Loss"
                    :display-value="`${row.original.speedLossPct.toFixed(1)}%`"
                    size="sm"
                  />
                  <div class="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2 text-xs font-data">
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">平均 STW</p>
                      <p class="tabular-nums">{{ row.original.avgStwKn?.toFixed(1) ?? '—' }} kt</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">平均 SFOC</p>
                      <p class="tabular-nums">{{ row.original.avgSfoc?.toFixed(0) ?? '—' }} g/kWh</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">平均負載率</p>
                      <p class="tabular-nums">{{ row.original.avgLoadPct?.toFixed(1) ?? '—' }} %MCR</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">平均貨載</p>
                      <p class="tabular-nums">{{ row.original.avgCargoOnBoardMt != null ? (row.original.avgCargoOnBoardMt / 1000).toFixed(0) + ' k MT' : '—' }}</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">資料期間</p>
                      <p class="tabular-nums">{{ row.original.dataSpanDays ?? '—' }} 天 / {{ row.original.totalVoyages }} 航次</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">養護事件數</p>
                      <p class="tabular-nums">{{ row.original.totalMaintEvents ?? '—' }} 次</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">最後養護類型</p>
                      <p>{{ row.original.lastEventType ?? '—' }}</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">上次清洗類型</p>
                      <p>{{ row.original.lastHullCleanType ?? '—' }}</p>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <StateDisplay
        v-if="filtered.length === 0"
        state="empty"
        empty-title="找不到符合條件的船舶"
        empty-hint="請調整篩選條件或關鍵字後再試一次。"
      />
    </div>
  </div>
</template>
