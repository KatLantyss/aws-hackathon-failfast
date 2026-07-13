<script setup lang="ts">
import { ref } from 'vue'
import type { VesselSummary } from '@/types/fleet'
import { fetchInspections } from '@/mock/api'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import FathometerGauge from '@/components/FathometerGauge.vue'
import HullFoulingDiagram from '@/components/HullFoulingDiagram.vue'
import { formatDate } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data: inspections, state } = useAsyncData(() => props.imo, fetchInspections)

const expandedId = ref<string | null>(null)
function toggle(id: string) {
  expandedId.value = expandedId.value === id ? null : id
}
</script>

<template>
  <div class="panel p-4 flex flex-col gap-3">
    <PanelTag code="UWI-01" />
    <StateDisplay
      v-if="state !== 'success'"
      :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
      empty-title="此船尚無水下檢查記錄"
      empty-hint="請聯絡驗船協調人員安排下一次 UWI 檢查。"
    />
    <ol v-else class="flex flex-col">
      <li v-for="insp in inspections" :key="insp.id" class="chart-divider py-4 first:border-t-0">
        <button class="w-full flex items-start gap-4 text-left" @click="toggle(insp.id)">
          <FathometerGauge
            size="sm"
            :value="insp.biofoulingScore"
            :grade="insp.foulingGrade"
            :display-value="`${insp.biofoulingScore}`"
          />
          <div class="flex-1">
            <p class="font-display text-sm">{{ formatDate(insp.date) }} · {{ insp.port }}</p>
            <p class="font-data text-xs text-[var(--color-ink-slate)]/60 mt-0.5">
              {{ insp.surveyor }} · {{ insp.method }}
            </p>
            <p class="text-sm mt-1 text-[var(--color-ink-slate)]/80">{{ insp.notes }}</p>
          </div>
          <span class="font-data text-xs text-[var(--color-ink-slate)]/50 shrink-0">
            {{ expandedId === insp.id ? '收合 ▾' : '展開 ▸' }}
          </span>
        </button>

        <div v-if="expandedId === insp.id" class="mt-4 pl-2 grid grid-cols-1 md:grid-cols-[220px_1fr] gap-6">
          <div class="flex flex-col items-center gap-2">
            <HullFoulingDiagram :sections="insp.hullSections" />
            <p class="font-data text-[10px] text-[var(--color-ink-slate)]/50">依區塊上色標示污損程度（示意）</p>
          </div>
          <div class="flex flex-col gap-3">
            <div class="grid grid-cols-2 gap-3 font-data text-sm">
              <div>
                <p class="text-xs font-body text-[var(--color-ink-slate)]/60">塗料破損率</p>
                <p>{{ insp.paintBreakdownPct.toFixed(1) }}%</p>
              </div>
              <div>
                <p class="text-xs font-body text-[var(--color-ink-slate)]/60">螺旋槳狀態</p>
                <p>{{ insp.propellerCondition }}</p>
              </div>
              <div>
                <p class="text-xs font-body text-[var(--color-ink-slate)]/60">是否建議清洗</p>
                <p :class="insp.cleaningRecommended.includes('PRIORITY') ? 'text-[var(--color-signal-red)]' : ''">
                  {{ insp.cleaningRecommended }}
                </p>
              </div>
              <div>
                <p class="text-xs font-body text-[var(--color-ink-slate)]/60">照片數量</p>
                <p>{{ insp.photoCount }} 張</p>
              </div>
            </div>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div
                v-for="n in Math.min(insp.photoCount, 8)"
                :key="n"
                class="aspect-square rounded-[2px] border chart-divider flex items-center justify-center text-[var(--color-ink-slate)]/30 bg-black/[0.03]"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <rect x="3" y="5" width="18" height="14" rx="1" stroke="currentColor" stroke-width="1.4" />
                  <circle cx="9" cy="10" r="1.6" stroke="currentColor" stroke-width="1.2" />
                  <path d="M4 17l5-5 3 3 4-5 4 5" stroke="currentColor" stroke-width="1.2" />
                </svg>
              </div>
            </div>
            <button
              class="w-fit border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              disabled
              title="Mock 資料無實際 PDF 檔案"
            >
              下載檢查報告 PDF
            </button>
          </div>
        </div>
      </li>
    </ol>
  </div>
</template>
