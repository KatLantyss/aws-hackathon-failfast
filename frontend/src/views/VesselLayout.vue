<script setup lang="ts">
import { computed, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { fetchCorrelation, fetchVesselData } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import { correlationDataKey, correlationStateKey } from '@/composables/useCorrelationContext'
import type { MaintenanceStatus } from '@/types/fleet'
import StateDisplay from '@/components/StateDisplay.vue'
import MaintenanceRequestModal from '@/components/MaintenanceRequestModal.vue'
import AlertThresholdModal from '@/components/AlertThresholdModal.vue'
import PanelTag from '@/components/PanelTag.vue'
import { URGENCY_LABEL, URGENCY_COLOR, MAINTENANCE_STATUS_LABEL, MAINTENANCE_STATUS_COLOR } from '@/utils/format'

const props = defineProps<{ imo: string }>()
const route = useRoute()

const { data: vessel, state } = useAsyncData(() => props.imo, fetchVesselData)

// ALT-01 拉出「維修效能分析」頁籤，改由這裡（頁籤外層）統一抓取維修關聯
// 資料並 provide 給該頁籤注入，讓 ⚡ 設定 Speed Loss 告警按鈕在切換頁籤時
// 仍持續顯示，也避免同一份資料在該頁籤內重複打一次 API
const { data: correlationData, state: correlationState } = useAsyncData(() => props.imo, fetchCorrelation)
provide(correlationDataKey, correlationData)
provide(correlationStateKey, correlationState)

// ALT-01 設定值放在頁籤外層持有，關閉彈窗、切換頁籤都不會重置
const alertModalOpen = ref(false)
const alertThresholdPct = ref(8) // Speed Loss % threshold
const alertDaysBefore = ref(14) // Alert N days before reaching threshold
const alertEnabled = ref(true)
const alertNotifyEmails = ref('')
watch(
  vessel,
  (v) => {
    if (v) alertNotifyEmails.value = `${v.name}@yangming.com.tw`
  },
  { immediate: true },
)

// 養護狀態徽章 — 放在 VesselLayout（頁籤外層），不受底下頁籤切換影響。純前端
// state，切換船舶時重新以後端 maintenanceStatus 初始化；「送出申請」不會呼叫
// 任何 API，只是把這顆 ref 樂觀更新為 'requested'。
const localMaintenanceStatus = ref<MaintenanceStatus>('normal')
watch(
  vessel,
  (v) => {
    if (v) localMaintenanceStatus.value = v.maintenanceStatus
  },
  { immediate: true },
)

const requestModalOpen = ref(false)
function onRequestSubmitted() {
  localMaintenanceStatus.value = 'requested'
}

const tabs = computed(() => [
  { to: `/vessels/${props.imo}/overview`, label: '總覽', name: 'vessel-overview' },
  { to: `/vessels/${props.imo}/hull-efficiency`, label: '🚢 船體能效管理', name: 'vessel-hull-efficiency' },
  { to: `/vessels/${props.imo}/noon-reports`, label: 'Noon Report', name: 'vessel-noon-reports' },
  { to: `/vessels/${props.imo}/inspections`, label: '維護紀錄', name: 'vessel-inspections' },
  { to: `/vessels/${props.imo}/speed-loss`, label: 'Speed Loss', name: 'vessel-speed-loss' },
  { to: `/vessels/${props.imo}/fuel-attribution`, label: 'Speed Loss 歸因', name: 'vessel-fuel-attribution' },
  { to: `/vessels/${props.imo}/fuel-prediction`, label: '油耗預測', name: 'vessel-fuel-prediction' },
  { to: `/vessels/${props.imo}/maintenance-correlation`, label: '維修效能分析', name: 'vessel-maintenance-correlation' },
])
</script>

<template>
  <div class="mx-auto max-w-[1440px] px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4">
    <StateDisplay
      v-if="state !== 'success'"
      :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
      empty-title="找不到此船舶"
      empty-hint="請確認 IMO 編號是否正確，或返回船隊列表重新選擇。"
    />
    <template v-else-if="vessel">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 class="text-2xl">{{ vessel.name }}</h1>
        </div>
        <span class="inline-flex items-center gap-2 font-data text-sm text-[var(--color-ink-slate)]/60">
          {{ vessel.type }}
        </span>
      </div>

      <!-- ═══ ALT-01: 設定 Speed Loss 告警 ═══ 從「維修效能分析」頁籤拉出來，
           收進按鈕＋彈窗，放在標題正下方、頁籤外層，切換頁籤時保持顯示 -->
      <div class="px-1">
        <button
          type="button"
          class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors inline-flex items-center gap-1.5"
          @click="alertModalOpen = true"
        >
          ⚡ 設定 Speed Loss 告警
        </button>
      </div>

      <AlertThresholdModal
        v-model:open="alertModalOpen"
        v-model:threshold-pct="alertThresholdPct"
        v-model:days-before="alertDaysBefore"
        v-model:enabled="alertEnabled"
        v-model:notify-emails="alertNotifyEmails"
        :vessel="vessel"
      />

      <!-- 維修急迫度／養護狀態 — 放在頁籤外層、標題正下方，切換頁籤時保持顯示 -->
      <div class="flex flex-wrap items-center gap-3 px-1">
        <span class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/60">維修急迫度</span>
        <span
          class="font-semibold text-sm px-2.5 py-0.5 rounded-[3px]"
          :style="{
            color: URGENCY_COLOR[vessel.maintenanceUrgency],
            background: `color-mix(in srgb, ${URGENCY_COLOR[vessel.maintenanceUrgency]} 14%, transparent)`,
          }"
        >{{ URGENCY_LABEL[vessel.maintenanceUrgency] }}</span>

        <span class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/60 ml-2">養護狀態</span>
        <span
          class="font-semibold text-sm px-2.5 py-0.5 rounded-[3px]"
          :style="{
            color: MAINTENANCE_STATUS_COLOR[localMaintenanceStatus],
            background: `color-mix(in srgb, ${MAINTENANCE_STATUS_COLOR[localMaintenanceStatus]} 14%, transparent)`,
          }"
        >{{ MAINTENANCE_STATUS_LABEL[localMaintenanceStatus] }}</span>

        <button
          type="button"
          class="border rounded-[2px] px-3 py-1 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
          @click="requestModalOpen = true"
        >
          申請養護
        </button>
      </div>

      <MaintenanceRequestModal
        v-model:open="requestModalOpen"
        :vessel="vessel"
        @submitted="onRequestSubmitted"
      />

      <!-- horizontal scroll on narrow screens instead of wrapping/overflowing;
           flex-nowrap + overflow-x-auto keeps the tab strip usable on mobile
           without redesigning it into a dropdown -->
      <nav
        class="flex flex-nowrap gap-1 border-b chart-divider overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        aria-label="船舶子導覽"
      >
        <RouterLink
          v-for="tab in tabs"
          :key="tab.to"
          :to="tab.to"
          class="font-display text-xs tracking-wide uppercase px-3 py-2 -mb-px border-b-2 transition-colors duration-150 whitespace-nowrap shrink-0"
          :class="
            route.name === tab.name
              ? 'border-[var(--color-brass-amber)] text-[var(--color-ink-slate)]'
              : 'border-transparent text-[var(--color-ink-slate)]/60 hover:text-[var(--color-ink-slate)]'
          "
        >
          {{ tab.label }}
        </RouterLink>
      </nav>

      <RouterView :vessel="vessel" :imo="imo" />
    </template>
  </div>
</template>
