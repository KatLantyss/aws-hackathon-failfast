<script setup lang="ts">
import { downloadTextFile } from '@/utils/download'

const props = defineProps<{
  modelValue: boolean
  title: string
  markdown: string
  filename: string
}>()

const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

function close() {
  emit('update:modelValue', false)
}

function download() {
  downloadTextFile(props.filename, props.markdown)
}
</script>

<template>
  <v-dialog :model-value="modelValue" max-width="640" @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-sheet rounded color="card" class="pa-4">
      <div class="d-flex align-center justify-space-between mb-3">
        <div class="d-flex align-center ga-2">
          <v-icon icon="mdi-file-document-outline" color="primary" />
          <span class="text-subtitle-1 font-weight-medium">{{ title }}</span>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </div>

      <v-sheet rounded color="surface" class="pa-3 report-preview" elevation="0">
        <pre>{{ markdown }}</pre>
      </v-sheet>

      <div class="d-flex justify-end ga-2 mt-4">
        <v-btn variant="text" @click="close">關閉</v-btn>
        <v-btn color="primary" prepend-icon="mdi-download" @click="download">下載 Markdown</v-btn>
      </div>
    </v-sheet>
  </v-dialog>
</template>

<style scoped>
.report-preview {
  max-height: 420px;
  overflow-y: auto;
}

.report-preview pre {
  white-space: pre-wrap;
  font-family: 'Consolas', monospace;
  font-size: 12px;
  color: #d7e6f5;
  margin: 0;
}
</style>
