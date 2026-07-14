<script setup lang="ts">
import { ref } from 'vue'
import type { VesselSummary } from '@/types/fleet'
import { getMaintenanceEvents } from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import { formatDate } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data, state } = useAsyncData(() => props.imo, getMaintenanceEvents)

const BASE_DATE = new Date('2020-01-01')
function dayToDate(day: number): string {
  const d = new Date(BASE_DATE)
  d.setDate(d.getDate() + Math.round(day))
  return d.toISOString().slice(0, 10)
}

const expandedDay = ref<number | null>(null)
function toggle(day: number) {
  expandedDay.value = expandedDay.value === day ? null : day
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  DD: '乾塢（Dry Dock）',
  UWC: '水下清洗（Hull Cleaning）',
  PP: '螺旋槳拋光（Propeller Polishing）',
  'UWC+PP': '清洗+拋光',
  'UWI+PP': '水下檢查+拋光',
  UWI: '水下檢查（UWI）',
}
const EVENT_TYPE_COLORS: Record<string, string> = {
  DD: '#C94B4B',
  UWC: '#2B6CB0',
  PP: '#C8A84B',
  'UWC+PP': '#6B46C1',
  'UWI+PP': '#319795',
  UWI: '#8FA6B2',
}
</script>

<template>
  <div class="panel p-4 flex flex-col gap-3">
    <PanelTag code="UWI-01" />
    <StateDisplay
      v-if="state !== 'success'"
      :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
      empty-title="此船尚無養護事件記錄"
      empty-hint="後端尚無此船的水下檢查或養護資料。"
    />
    <ol v-else-if="data?.events.length" class="flex flex-col">
      <li
        v-for="evt in [...(data?.events ?? [])].sort((a, b) => b.event_day - a.event_day)"
        :key="`${evt.event_type}-${evt.event_day}`"
        class="chart-divider py-4 first:border-t-0"
      >
        <button class="w-full flex items-start gap-4 text-left" @click="toggle(evt.event_day)">
          <div
            class="w-10 h-10 rounded-[3px] flex items-center justify-center text-white text-xs font-display font-bold shrink-0"
            :style="{ background: EVENT_TYPE_COLORS[evt.event_type] ?? '#6B7A8D' }"
          >
            {{ evt.event_type.split('+')[0] }}
          </div>
          <div class="flex-1">
            <p class="font-display text-sm">{{ EVENT_TYPE_LABELS[evt.event_type] ?? evt.event_type }}</p>
            <p class="font-data text-xs text-[var(--color-ink-slate)]/60 mt-0.5">
              Day {{ evt.event_day }} · {{ formatDate(dayToDate(evt.event_day)) }}
            </p>
          </div>
          <span class="font-data text-xs text-[var(--color-ink-slate)]/50 shrink-0">
            {{ expandedDay === evt.event_day ? '收合 ▾' : '展開 ▸' }}
          </span>
        </button>

        <div v-if="expandedDay === evt.event_day" class="mt-4 pl-14 grid grid-cols-2 md:grid-cols-3 gap-4 font-data text-sm">
          <div v-if="evt.propeller_condition">
            <p class="text-xs font-body text-[var(--color-ink-slate)]/60">螺旋槳狀態</p>
            <p>{{ evt.propeller_condition }}</p>
          </div>
          <div v-if="evt.hull_fouling_type">
            <p class="text-xs font-body text-[var(--color-ink-slate)]/60">船殼污損類型</p>
            <p>{{ evt.hull_fouling_type }}</p>
          </div>
          <div v-if="evt.hull_coating_condition">
            <p class="text-xs font-body text-[var(--color-ink-slate)]/60">塗裝狀態</p>
            <p>{{ evt.hull_coating_condition }}</p>
          </div>
          <div v-if="evt.cavitation_found !== null && evt.cavitation_found !== undefined">
            <p class="text-xs font-body text-[var(--color-ink-slate)]/60">空蝕發現</p>
            <p>{{ evt.cavitation_found }}</p>
          </div>
          <div v-if="evt.draft_fwd_m !== null && evt.draft_fwd_m !== undefined">
            <p class="text-xs font-body text-[var(--color-ink-slate)]/60">前吃水</p>
            <p>{{ evt.draft_fwd_m }} m</p>
          </div>
          <div v-if="evt.draft_aft_m !== null && evt.draft_aft_m !== undefined">
            <p class="text-xs font-body text-[var(--color-ink-slate)]/60">後吃水</p>
            <p>{{ evt.draft_aft_m }} m</p>
          </div>
        </div>
      </li>
    </ol>
    <p v-else class="text-sm text-[var(--color-ink-slate)]/50">此船尚無養護記錄。</p>
  </div>
</template>
