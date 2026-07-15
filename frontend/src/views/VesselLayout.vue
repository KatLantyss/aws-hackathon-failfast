<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { fetchVesselData } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import type { MaintenanceStatus } from '@/types/fleet'
import StateDisplay from '@/components/StateDisplay.vue'
import MaintenanceRequestModal from '@/components/MaintenanceRequestModal.vue'
import { URGENCY_LABEL, URGENCY_COLOR, MAINTENANCE_STATUS_LABEL, MAINTENANCE_STATUS_COLOR } from '@/utils/format'

const props = defineProps<{ imo: string }>()
const route = useRoute()

const { data: vessel, state } = useAsyncData(() => props.imo, fetchVesselData)

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
  { to: `/vessels/${props.imo}/noon-reports`, label: 'Noon Report', name: 'vessel-noon-reports' },
  { to: `/vessels/${props.imo}/inspections`, label: '維護紀錄', name: 'vessel-inspections' },
  { to: `/vessels/${props.imo}/speed-loss`, label: 'Speed Loss', name: 'vessel-speed-loss' },
  // Renamed from "油耗歸因": the underlying endpoint attributes SPEED LOSS
  // (slip%) to hull vs propeller, not fuel consumption — matches
  // main-requirement.md's ISO 19030 ask "② 船體 vs 螺旋槳歸因", not a real
  // fuel waterfall. See docs/frontend-backend-integration-status.html §7.
  { to: `/vessels/${props.imo}/fuel-attribution`, label: '速損歸因', name: 'vessel-fuel-attribution' },
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
          <RouterLink to="/vessels" class="text-xs text-[var(--color-ink-slate)]/60 hover:text-[var(--color-brass-amber)]"
            >← 返回船隊列表</RouterLink
          >
          <h1 class="text-2xl flex items-center gap-3 mt-1">
            {{ vessel.name }}
            <span class="font-data text-sm normal-case tracking-normal text-[var(--color-ink-slate)]/60"
              >IMO {{ vessel.imo }}</span
            >
          </h1>
        </div>
        <span class="inline-flex items-center gap-2 font-data text-sm text-[var(--color-ink-slate)]/60">
          {{ vessel.type }}
        </span>
      </div>

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

        <span v-if="vessel.lastHullCleanType" class="font-data text-xs text-[var(--color-ink-slate)]/50">
          上次清洗：{{ vessel.lastHullCleanType }}
        </span>
        <span v-if="vessel.lastEventType" class="font-data text-xs text-[var(--color-ink-slate)]/50">
          · 最後養護：{{ vessel.lastEventType }}
        </span>
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
