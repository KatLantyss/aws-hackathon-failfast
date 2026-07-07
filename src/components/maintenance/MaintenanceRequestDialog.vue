<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMaintenanceRequestStore } from '@/stores/maintenanceRequestStore'
import type { Vessel } from '@/data/mockFleet'

const props = defineProps<{
  modelValue: boolean
  vessel: Vessel | null
  defaultDate: string
}>()

const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const store = useMaintenanceRequestStore()

const date = ref(props.defaultDate)
const port = ref('')
const note = ref('')
const notifyTeam = ref(true)
const snackbar = ref(false)
const snackbarText = ref('')

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      date.value = props.defaultDate
      port.value = ''
      note.value = ''
      notifyTeam.value = true
    }
  }
)

function close() {
  emit('update:modelValue', false)
}

function submit() {
  if (!props.vessel) return
  const req = store.createRequest({
    vesselId: props.vessel.id,
    vesselName: props.vessel.name,
    requestedDate: date.value,
    port: port.value || '待港務確認',
    note: note.value,
    notifyTeam: notifyTeam.value
  })
  close()
  snackbarText.value = `已建立水下清潔申請 ${req.id}，可於「維修排程」頁追蹤進度`
  snackbar.value = true
}
</script>

<template>
  <v-dialog :model-value="modelValue" max-width="480" @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-sheet rounded color="card" class="pa-4">
      <div class="d-flex align-center justify-space-between mb-3">
        <div class="d-flex align-center ga-2">
          <v-icon icon="mdi-calendar-check-outline" color="primary" />
          <span class="text-subtitle-1 font-weight-medium">安排水下清潔 — {{ vessel?.name }}</span>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </div>

      <v-text-field v-model="date" type="date" label="建議清潔日期" density="comfortable" class="mb-2" />
      <v-text-field v-model="port" label="靠港地點" placeholder="例如：高雄港" density="comfortable" class="mb-2" />
      <v-textarea v-model="note" label="備註" rows="3" density="comfortable" class="mb-2" />
      <v-checkbox v-model="notifyTeam" label="送出後通知節能小組" density="comfortable" hide-details class="mb-2" />

      <div class="d-flex justify-end ga-2 mt-2">
        <v-btn variant="text" @click="close">取消</v-btn>
        <v-btn color="primary" prepend-icon="mdi-send" @click="submit">送出申請</v-btn>
      </div>
    </v-sheet>
  </v-dialog>

  <v-snackbar v-model="snackbar" color="secondary" :timeout="3500">
    {{ snackbarText }}
  </v-snackbar>
</template>
