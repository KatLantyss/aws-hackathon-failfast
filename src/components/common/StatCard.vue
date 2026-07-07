<script setup lang="ts">
defineProps<{
  icon: string
  label: string
  value: string | number
  suffix?: string
  color?: string
  hint?: string
}>()
</script>

<template>
  <v-sheet rounded color="card" class="pa-4 stat-card" elevation="0">
    <div class="d-flex align-center justify-space-between mb-2">
      <span class="text-caption text-medium-emphasis">{{ label }}</span>
      <v-icon :icon="icon" :color="color ?? 'primary'" size="20" />
    </div>
    <div class="d-flex align-baseline">
      <span class="text-h5 font-weight-bold">{{ value }}</span>
      <span v-if="suffix" class="text-caption text-medium-emphasis ml-1">{{ suffix }}</span>
    </div>
    <div v-if="hint" class="text-caption text-medium-emphasis mt-1">{{ hint }}</div>
  </v-sheet>
</template>

<style scoped>
.stat-card {
  border: 1px solid rgba(255, 255, 255, 0.06);
  height: 100%;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: rgba(0, 194, 255, 0.35);
  box-shadow: 0 8px 20px rgba(0, 194, 255, 0.12);
}
</style>
