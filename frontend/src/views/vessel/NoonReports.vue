<script setup lang="ts">
import { computed, ref } from 'vue'
import type { VesselSummary } from '@/types/fleet'
import { fetchNoonReports } from '@/mock/api'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import { formatDate } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()

const { data, state } = useAsyncData(() => props.imo, fetchNoonReports)

const startDate = ref('')
const endDate = ref('')

const filteredReports = computed(() => {
  if (!data.value) return []
  return data.value.reports.filter((r) => {
    if (startDate.value && r.date < startDate.value) return false
    if (endDate.value && r.date > endDate.value) return false
    return true
  })
})

// Show a manageable window by default (most recent 60 entries) while still
// allowing the date filters above to widen the range.
const visibleReports = computed(() => {
  const list = filteredReports.value
  if (startDate.value || endDate.value) return list
  return list.slice(-60)
})

function exportCsv() {
  const rows = filteredReports.value.length ? filteredReports.value : visibleReports.value
  const header = ['Date', 'Lat', 'Lon', 'ObservedSpeedKt', 'CorrectedSpeedKt', 'SpeedLossPct', 'FuelMt', 'Beaufort', 'DraftFwd', 'DraftAft', 'LoadCondition', 'Anomaly']
  const lines = rows.map((r) =>
    [r.date, r.lat, r.lon, r.observedSpeedKt, r.correctedSpeedKt, r.speedLossPct, r.fuelConsumptionMt, r.beaufort, r.draftFwd, r.draftAft, r.loadCondition, r.isAnomaly ? 'Y' : 'N'].join(','),
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
      <PanelTag code="NR-01" />
      <div class="flex items-center gap-2 text-sm">
        <label class="flex items-center gap-1">
          <span class="text-[var(--color-ink-slate)]/60 text-xs">起</span>
          <input v-model="startDate" type="date" class="border rounded-[2px] px-2 py-1 font-data text-xs" />
        </label>
        <label class="flex items-center gap-1">
          <span class="text-[var(--color-ink-slate)]/60 text-xs">迄</span>
          <input v-model="endDate" type="date" class="border rounded-[2px] px-2 py-1 font-data text-xs" />
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
      empty-title="所選日期區間內無資料"
      empty-hint="請放寬日期篩選範圍。"
    />
    <div v-else class="overflow-x-auto max-h-[640px] overflow-y-auto">
      <table class="w-full text-sm">
        <thead class="sticky top-0 bg-[var(--color-chart-paper)]">
          <tr class="chart-divider">
            <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">日期</th>
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
            :key="r.date"
            class="chart-divider group relative"
            :class="r.isAnomaly ? 'bg-[var(--color-signal-red)]/10' : ''"
            :title="r.isAnomaly ? r.anomalyReason ?? undefined : undefined"
          >
            <td class="px-3 py-1.5 font-data whitespace-nowrap">{{ formatDate(r.date) }}</td>
            <td class="px-3 py-1.5 font-data text-xs">{{ r.lat.toFixed(2) }}, {{ r.lon.toFixed(2) }}</td>
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
              <span v-if="r.isAnomaly" class="ml-1 text-xs text-[var(--color-signal-red)] font-semibold">⚠ 異常</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="text-xs text-[var(--color-ink-slate)]/50 mt-2 px-1">
        滑鼠移至標紅列可查看異常判定原因。預設顯示最近 60 筆，可用日期篩選查看完整區間。日期為本船資料起始後的相對天數換算而成（後端未提供實際日曆日期），位置座標為示意；其餘欄位（航速、油耗、吃水、海況、Speed Loss）皆為後端真實記錄。異常為 Z-score / Slip 範圍統計判定。
      </p>
    </div>
  </div>
</template>
