<script setup lang="ts">
export interface HistoryEventDetail {
  date: string
  vessel: string
  type: string
  note: string
  detail: string
  zones?: { name: string; severity: string }[]
  metrics?: { label: string; before: string; after: string }[]
}

defineProps<{
  modelValue: boolean
  event: HistoryEventDetail | null
}>()

const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const severityColor = (severity: string) =>
  severity === '嚴重' ? 'error' : severity === '中度' ? 'warning' : 'secondary'
</script>

<template>
  <v-dialog :model-value="modelValue" max-width="520" @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-sheet v-if="event" rounded color="card" class="pa-4">
      <div class="d-flex align-center justify-space-between mb-3">
        <div class="d-flex align-center ga-2">
          <v-icon icon="mdi-file-search-outline" color="primary" />
          <span class="text-subtitle-1 font-weight-medium">{{ event.vessel }} · {{ event.type }}</span>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('update:modelValue', false)" />
      </div>

      <div class="text-caption text-medium-emphasis mb-3">{{ event.date }}</div>

      <v-sheet rounded color="surface" class="pa-3 mb-3" elevation="0">
        <div class="text-caption text-medium-emphasis mb-1">AI 完整分析</div>
        <p class="text-body-2 mb-0">{{ event.detail }}</p>
      </v-sheet>

      <div v-if="event.zones?.length" class="mb-3">
        <div class="text-caption text-medium-emphasis mb-2">偵測分區</div>
        <div class="d-flex flex-wrap ga-2">
          <v-chip v-for="z in event.zones" :key="z.name" size="small" :color="severityColor(z.severity)" variant="tonal">
            {{ z.name }} · {{ z.severity }}
          </v-chip>
        </div>
      </div>

      <v-table v-if="event.metrics?.length" density="compact" class="metrics-table">
        <thead>
          <tr>
            <th>指標</th>
            <th>清潔前</th>
            <th>清潔後</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in event.metrics" :key="m.label">
            <td>{{ m.label }}</td>
            <td class="text-medium-emphasis">{{ m.before }}</td>
            <td class="text-secondary">{{ m.after }}</td>
          </tr>
        </tbody>
      </v-table>
    </v-sheet>
  </v-dialog>
</template>

<style scoped>
.metrics-table {
  background: transparent;
}
</style>
