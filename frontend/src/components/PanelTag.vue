<script setup lang="ts">
// Coordinate-style panel identifier tag per design_docs 3.4, e.g. "SPD-01".
defineProps<{ code: string }>()
</script>

<template>
  <span class="panel-tag">{{ code }}</span>
</template>
