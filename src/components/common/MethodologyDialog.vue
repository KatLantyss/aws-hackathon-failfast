<script setup lang="ts">
import IsoMethodologyCard from '@/components/common/IsoMethodologyCard.vue'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()
</script>

<template>
  <v-dialog :model-value="modelValue" max-width="640" @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-sheet rounded color="card" class="pa-4">
      <div class="d-flex align-center justify-space-between mb-3">
        <div class="d-flex align-center ga-2">
          <v-icon icon="mdi-file-certificate-outline" color="primary" />
          <span class="text-subtitle-1 font-weight-medium">計算方法論 / ISO 標準對照</span>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('update:modelValue', false)" />
      </div>
      <div class="methodology-body">
        <IsoMethodologyCard />
      </div>
    </v-sheet>
  </v-dialog>
</template>

<style scoped>
.methodology-body {
  max-height: 60vh;
  overflow-y: auto;
}
</style>
