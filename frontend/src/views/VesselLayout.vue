<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { fetchVesselData } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'

const props = defineProps<{ imo: string }>()
const route = useRoute()

const { data: vessel, state } = useAsyncData(() => props.imo, fetchVesselData)

const tabs = computed(() => [
  { to: `/vessels/${props.imo}/overview`, label: '總覽', name: 'vessel-overview' },
  { to: `/vessels/${props.imo}/noon-reports`, label: 'Noon Report', name: 'vessel-noon-reports' },
  { to: `/vessels/${props.imo}/inspections`, label: '水下檢查', name: 'vessel-inspections' },
  { to: `/vessels/${props.imo}/speed-loss`, label: 'Speed Loss', name: 'vessel-speed-loss' },
  { to: `/vessels/${props.imo}/fuel-attribution`, label: '油耗歸因', name: 'vessel-fuel-attribution' },
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
          {{ vessel.type }} · 設計航速 {{ vessel.designSpeedKt }} kt
        </span>
      </div>

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
