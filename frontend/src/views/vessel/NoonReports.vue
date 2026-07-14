<script setup lang="ts">
import { computed, ref } from 'vue'
import type { VesselSummary, NoonReportEntry } from '@/types/fleet'
import { getNoonReports } from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()

async function fetchReports(imo: string): Promise<{ vessel: VesselSummary; reports: NoonReportEntry[] }> {
  const resp = await getNoonReports(imo, { limit: 5000 })
  const reports: NoonReportEntry[] = resp.records.map((r) => ({
    day: r.noon_day,
    lat: 0,
    lon: 0,
    observedSpeedKt: r.avg_speed_kn ?? 0,
    correctedSpeedKt: r.speed_through_water ?? 0,
    speedLossPct: 0,
    fuelConsumptionMt: r.me_consumption ?? 0,
    beaufort: r.wind_scale ?? 0,
    seaState: r.wind_scale ?? 0,
    draftFwd: r.fore_draft ?? 0,
    draftAft: r.aft_draft ?? 0,
    loadCondition: (r.cargo_on_board ?? 0) > 1000 ? 'laden' : 'ballast',
  }))
  return { vessel: props.vessel, reports }
}

const { data, state } = useAsyncData(() => props.imo, fetchReports)

const startDayInput = ref('')
const endDayInput = ref('')
const startDay = computed(() => (startDayInput.value === '' ? null : Number(startDayInput.value)))
const endDay = computed(() => (endDayInput.value === '' ? null : Number(endDayInput.value)))

const filteredReports = computed(() => {
  if (!data.value) return []
  return data.value.reports.filter((r) => {
    if (startDay.value != null && r.day < startDay.value) return false
    if (endDay.value != null && r.day > endDay.value) return false
    return true
  })
})

const visibleReports = computed(() => {
  const list = filteredReports.value
  if (startDay.value != null || endDay.value != null) return list
  return list.slice(-60)
})

function exportCsv() {
  const rows = filteredReports.value.length ? filteredReports.value : visibleReports.value
  const header = ['Day', 'ObservedSpeedKt', 'STW', 'FuelMt', 'Beaufort', 'DraftFwd', 'DraftAft', 'LoadCondition']
  const lines = rows.map((r) =>
    [r.day, r.observedSpeedKt, r.correctedSpeedKt, r.fuelConsumptionMt, r.beaufort, r.draftFwd, r.draftAft, r.loadCondition].join(','),
  )
  const csv = [header.join(','), ...lines].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${props.vessel.name.replace(/\s+/g, '_')}_noon_reports.csv`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="panel p-4 flex flex-col gap-3">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <PanelTag code="NR-01" />
        <span v-if="data" class="text-xs text-[var(--color-ink-slate)]/50 font-data">
          共 {{ data.reports.length.toLocaleString() }} 筆{{ filteredReports.length !== data.reports.length ? `（篩選後 ${filteredReports.length.toLocaleString()} 筆）` : '' }}
        </span>
      </div>
      <div class="flex items-center gap-2 text-sm">
        <label class="flex items-center gap-1">
          <span class="text-[var(--color-ink-slate)]/60 text-xs">起 (Day)</span>
          <input v-model="startDayInput" type="number" class="border rounded-[2px] px-2 py-1 font-data text-xs w-20" />
        </label>
        <label class="flex items-center gap-1">
          <span class="text-[var(--color-ink-slate)]/60 text-xs">迄 (Day)</span>
          <input v-model="endDayInput" type="number" class="border rounded-[2px] px-2 py-1 font-data text-xs w-20" />
        </label>
        <button
          class="border rounded-[2px] px-3 py-1 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
          @click="exportCsv"
        >
          匯出 CSV
        </button>
      </div>
    </div>

    <StateDisplay
      v-if="state !== 'success'"
      :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
      empty-title="此船尚無 Noon Report 記錄"
    />
    <StateDisplay
      v-else-if="visibleReports.length === 0"
      state="empty"
      empty-title="所選 Day 區間內無資料"
      empty-hint="請放寬篩選範圍。"
    />
    <div v-else class="overflow-x-auto max-h-[640px] overflow-y-auto">
      <table class="w-full text-sm">
        <thead class="sticky top-0 bg-[var(--color-chart-paper)]">
          <tr class="chart-divider">
            <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">Day</th>
            <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">位置</th>
            <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">航速(觀測)</th>
            <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">航速(修正後)</th>
            <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">油耗 MT/日</th>
            <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">海況(BF)</th>
            <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">吃水(F/A)</th>
            <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">狀態</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in visibleReports"
            :key="r.day"
            class="chart-divider group relative"
          >
            <td class="px-3 py-1.5 font-data whitespace-nowrap">{{ r.day }}</td>
            <td class="px-3 py-1.5 font-data text-xs text-[var(--color-ink-slate)]/50">—</td>
            <td class="px-3 py-1.5 font-data text-right">{{ r.observedSpeedKt.toFixed(1) }}</td>
            <td class="px-3 py-1.5 font-data text-right">{{ r.correctedSpeedKt.toFixed(1) }}</td>
            <td class="px-3 py-1.5 font-data text-right">{{ r.fuelConsumptionMt.toFixed(1) }}</td>
            <td class="px-3 py-1.5 font-data text-right">{{ r.beaufort }}</td>
            <td class="px-3 py-1.5 font-data text-right">{{ r.draftFwd.toFixed(1) }}/{{ r.draftAft.toFixed(1) }}</td>
            <td class="px-3 py-1.5">
              <span
                class="text-xs px-1.5 py-0.5 rounded-[2px] border font-body"
                :class="r.loadCondition === 'laden' ? 'border-[var(--color-ink-slate)]/40' : 'border-[var(--color-brass-amber)]/60 text-[var(--color-brass-amber)]'"
              >
                {{ r.loadCondition === 'laden' ? 'Laden' : 'Ballast' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="text-xs text-[var(--color-ink-slate)]/50 mt-2 px-1">
        預設顯示最近 60 筆，可用 Day 篩選查看完整區間。
      </p>
    </div>
  </div>
</template>
