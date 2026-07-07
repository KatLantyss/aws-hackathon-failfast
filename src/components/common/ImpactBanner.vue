<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '@/stores/fleetStore'
import { predictMaintenanceWindow } from '@/utils/predictiveMaintenance'

// IMO 建議之 VLSFO 燃油碳排放係數 (tCO2 / t 燃油)，用於將節省油耗換算成減碳量估算
const CO2_FACTOR_T_PER_T_FUEL = 3.15

const fleet = useFleetStore()

const impact = computed(() => {
  const predictions = fleet.vessels.map((v) => predictMaintenanceWindow(v))
  const dailySavingSum = predictions.reduce((s, p) => s + p.estFuelSavingTDay, 0)
  const annualFuelSaving = Math.round(dailySavingSum * 365)
  const annualCo2Saving = Math.round(annualFuelSaving * CO2_FACTOR_T_PER_T_FUEL)
  const attentionCount = fleet.vessels.filter((v) => v.status !== 'normal').length
  return { annualFuelSaving, annualCo2Saving, attentionCount }
})
</script>

<template>
  <v-sheet rounded color="card" class="pa-4 mb-4 impact-banner" elevation="0">
    <div class="d-flex align-center ga-2 mb-3">
      <v-icon icon="mdi-leaf-circle-outline" color="secondary" />
      <span class="text-subtitle-2 font-weight-medium">節能減碳潛在效益（依目前預判排程估算）</span>
    </div>
    <div class="d-flex flex-wrap ga-6">
      <div class="impact-metric">
        <div class="impact-value text-secondary">
          {{ impact.annualFuelSaving.toLocaleString() }}<span class="impact-unit">t/年</span>
        </div>
        <div class="text-caption text-medium-emphasis">預估年化可節省油耗</div>
      </div>
      <div class="impact-metric">
        <div class="impact-value text-primary">
          {{ impact.annualCo2Saving.toLocaleString() }}<span class="impact-unit">tCO₂/年</span>
        </div>
        <div class="text-caption text-medium-emphasis">預估年化減少碳排放</div>
      </div>
      <div class="impact-metric">
        <div class="impact-value text-warning">
          {{ impact.attentionCount }}<span class="impact-unit">艘</span>
        </div>
        <div class="text-caption text-medium-emphasis">目前待安排水下清潔</div>
      </div>
    </div>
    <div class="text-caption text-medium-emphasis mt-3">
      碳排放依 IMO 建議燃油排放係數 {{ CO2_FACTOR_T_PER_T_FUEL }} tCO₂/t 估算，實際數值待節能小組以正式公式覆核。
    </div>
  </v-sheet>
</template>

<style scoped>
.impact-banner {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(0, 224, 160, 0.25);
}

.impact-banner::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 15% 20%, rgba(0, 224, 160, 0.14), transparent 60%);
  pointer-events: none;
  animation: impact-glow 4s ease-in-out infinite;
}

@keyframes impact-glow {
  0%, 100% { opacity: 0.7; }
  50% { opacity: 1; }
}

.impact-metric {
  min-width: 160px;
  position: relative;
  z-index: 1;
}

.impact-value {
  font-size: 32px;
  font-weight: 700;
  line-height: 1;
}

.impact-unit {
  font-size: 13px;
  font-weight: 500;
  margin-left: 4px;
  opacity: 0.7;
}
</style>
