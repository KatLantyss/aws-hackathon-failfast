<script setup lang="ts">
import type { MaintenanceRecommendation } from '@/types/fleet'
import PanelTag from '@/components/PanelTag.vue'
import { formatDay, formatUsd, CONFIDENCE_LABEL } from '@/utils/format'

defineProps<{ data: MaintenanceRecommendation }>()
</script>

<template>
  <div class="panel p-4 border-l-4" style="border-left-color: var(--color-brass-amber)">
    <PanelTag code="ADV-02" class="mb-2" />
    <p class="font-display text-sm mb-2">建議執行維修</p>
    <p class="font-data text-xl text-[var(--color-brass-amber)]">
      {{ formatDay(data.windowStartDay) }} — {{ formatDay(data.windowEndDay) }}
    </p>
    <div class="flex items-center gap-6 mt-3 text-sm">
      <div>
        <p class="text-xs text-[var(--color-ink-slate)]/60">預期節省金額</p>
        <p class="font-data text-lg text-[var(--color-fathom-teal)]">{{ formatUsd(data.estimatedSavingUsd) }}</p>
      </div>
      <div>
        <p class="text-xs text-[var(--color-ink-slate)]/60">信心程度</p>
        <p class="font-data text-lg">{{ CONFIDENCE_LABEL[data.confidence] }}</p>
      </div>
    </div>
    <p class="text-sm text-[var(--color-ink-slate)]/80 mt-3">{{ data.reasoning }}</p>
  </div>
</template>
