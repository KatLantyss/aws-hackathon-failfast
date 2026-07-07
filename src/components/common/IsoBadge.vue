<script setup lang="ts">
import { ref } from 'vue'
import MethodologyDialog from '@/components/common/MethodologyDialog.vue'

const open = ref(false)
</script>

<template>
  <v-chip
    color="primary"
    variant="tonal"
    size="small"
    prepend-icon="mdi-file-certificate-outline"
    class="iso-badge"
    @click="open = true"
  >
    依 ISO 15016 / ISO 19030 標準計算
  </v-chip>
  <MethodologyDialog v-model="open" />
</template>

<style scoped>
.iso-badge {
  cursor: pointer;
}
</style>
