<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { VesselSummary } from '@/types/fleet'
import FathometerGauge from '@/components/FathometerGauge.vue'
import { URGENCY_LABEL } from '@/utils/format'
import { useChatContextStore } from '@/stores/chatContext'

defineProps<{ vessels: VesselSummary[] }>()

const router = useRouter()
const chatContext = useChatContextStore()

function goToVessel(imo: string) {
  chatContext.closeChat()
  router.push(`/vessels/${imo}/overview`)
}
</script>

<template>
  <ul class="flex flex-col gap-2">
    <li
      v-for="(v, i) in vessels"
      :key="v.imo"
      class="flex items-center gap-3 p-2 rounded-[2px] border border-[var(--color-ink-slate)]/10 hover:border-[var(--color-fathom-teal)]/50 cursor-pointer transition-colors"
      @click="goToVessel(v.imo)"
    >
      <span class="font-data text-xs text-[var(--color-ink-slate)]/50 w-4">{{ i + 1 }}</span>
      <FathometerGauge size="sm" :value="Math.min(100, v.speedLossPct * 8)" :grade="v.foulingGrade" :display-value="`${v.speedLossPct.toFixed(1)}%`" />
      <div class="flex-1">
        <p class="font-display text-sm">{{ v.name }}</p>
        <p class="text-xs text-[var(--color-ink-slate)]/60">緊急程度：{{ URGENCY_LABEL[v.maintenanceUrgency] }}</p>
      </div>
    </li>
  </ul>
</template>
