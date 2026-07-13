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
import { fetchFleetVessels } from '@/mock/api'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import FathometerGauge from '@/components/FathometerGauge.vue'
import type { VesselSummary } from '@/types/fleet'
import { formatDate, STATUS_LABEL, STATUS_COLOR, speedLossColor } from '@/utils/format'

const router = useRouter()
const { data: vessels, state } = useAsyncData(() => true, fetchFleetVessels)

const typeFilter = ref('all')
const statusFilter = ref('all')
const keyword = ref('')
const expandedImo = ref<string | null>(null)
const sorting = ref<SortingState>([])

const vesselTypes = computed(() => {
  if (!vessels.value) return []
  return Array.from(new Set(vessels.value.map((v) => v.type)))
})

const filtered = computed<VesselSummary[]>(() => {
  if (!vessels.value) return []
  return vessels.value.filter((v) => {
    if (typeFilter.value !== 'all' && v.type !== typeFilter.value) return false
    if (statusFilter.value !== 'all' && v.status !== statusFilter.value) return false
    if (keyword.value && !`${v.name} ${v.imo}`.toLowerCase().includes(keyword.value.toLowerCase())) return false
    return true
  })
})

const columns: ColumnDef<VesselSummary>[] = [
  { accessorKey: 'name', header: '船名' },
  { accessorKey: 'imo', header: 'IMO' },
  { accessorKey: 'type', header: '船型' },
  {
    id: 'age',
    header: '船齡',
    accessorFn: (row) => new Date().getFullYear() - row.builtYear,
  },
  { accessorKey: 'speedLossPct', header: 'Speed Loss %' },
  {
    id: 'lastClean',
    header: '上次坐塢日',
    accessorFn: (row) => row.lastDrydockDate,
  },
  {
    id: 'nextWindow',
    header: '下次建議維修窗口',
    accessorFn: (row) => row.nextRecommendedWindow.start,
  },
  { accessorKey: 'status', header: '狀態' },
]

const table = useVueTable({
  get data() {
    return filtered.value
  },
  columns,
  state: {
    get sorting() {
      return sorting.value
    },
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
      <label class="flex items-center gap-2 text-sm">
        <span class="col-head">狀態</span>
        <select v-model="statusFilter" class="field">
          <option value="all">全部</option>
          <option value="underway">航行中</option>
          <option value="moored">靠泊中</option>
          <option value="anchored">錨泊中</option>
        </select>
      </label>
      <label class="flex items-center gap-2 text-sm flex-1 min-w-[200px]">
        <span class="col-head">關鍵字</span>
        <input v-model="keyword" type="search" placeholder="船名 / IMO" class="field flex-1" />
      </label>
    </div>

    <StateDisplay v-if="state !== 'success'" :state="state === 'error' ? 'error' : 'loading'" />

    <div v-else class="panel panel--accent overflow-x-auto">
      <table class="w-full text-sm">
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
              <td class="px-2 py-2 text-center">
                <button
                  class="text-[var(--color-ink-slate)]/60 hover:text-[var(--color-ink-slate)]"
                  aria-label="展開風險量表"
                  @click.stop="toggleExpand(row.original.imo)"
                >
                  {{ expandedImo === row.original.imo ? '▾' : '▸' }}
                </button>
              </td>
              <td class="px-3 py-3 font-display text-[15px] tracking-wide">{{ row.original.name }}</td>
              <td class="px-3 py-3 font-data text-[var(--color-ink-muted)]">{{ row.original.imo }}</td>
              <td class="px-3 py-3">{{ row.original.type }}</td>
              <td class="px-3 py-3 font-data text-right tabular-nums">{{ new Date().getFullYear() - row.original.builtYear }}</td>
              <td class="px-3 py-3 text-right">
                <span
                  class="font-data font-bold tabular-nums px-1.5 py-0.5 rounded-[3px]"
                  :style="{
                    color: speedLossColor(row.original.speedLossPct),
                    background: `color-mix(in srgb, ${speedLossColor(row.original.speedLossPct)} 12%, transparent)`,
                  }"
                >
                  {{ row.original.speedLossPct.toFixed(1) }}%
                </span>
              </td>
              <td class="px-3 py-3 font-data text-[var(--color-ink-muted)]">{{ formatDate(row.original.lastDrydockDate) }}</td>
              <td class="px-3 py-3 font-data text-[var(--color-ink-muted)]">
                {{ formatDate(row.original.nextRecommendedWindow.start) }} – {{ formatDate(row.original.nextRecommendedWindow.end) }}
              </td>
              <td class="px-3 py-3">
                <span
                  class="inline-flex items-center gap-2 text-xs font-medium px-2 py-1 rounded-full border"
                  :style="{
                    color: STATUS_COLOR[row.original.status],
                    borderColor: `color-mix(in srgb, ${STATUS_COLOR[row.original.status]} 35%, transparent)`,
                    background: `color-mix(in srgb, ${STATUS_COLOR[row.original.status]} 10%, transparent)`,
                  }"
                >
                  <span class="status-dot" style="width: 8px; height: 8px" :style="{ background: STATUS_COLOR[row.original.status] }" />
                  {{ STATUS_LABEL[row.original.status] }}
                </span>
              </td>
            </tr>
            <tr v-if="expandedImo === row.original.imo" class="chart-divider bg-black/[0.015]">
              <td colspan="9" class="px-6 py-4">
                <FathometerGauge
                  :value="Math.min(100, row.original.speedLossPct * 8)"
                  :grade="row.original.foulingGrade"
                  label="船體污損 / Speed Loss"
                  :display-value="`${row.original.speedLossPct.toFixed(1)}%`"
                  size="sm"
                />
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
