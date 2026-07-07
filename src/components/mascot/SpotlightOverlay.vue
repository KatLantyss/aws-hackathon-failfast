<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick } from 'vue'
import { useSpotlightStore } from '@/stores/spotlightStore'

const spotlight = useSpotlightStore()
const rect = ref<{ top: number; left: number; width: number; height: number } | null>(null)
let raf = 0

function update() {
  if (!spotlight.targetSelector) {
    rect.value = null
    return
  }
  const el = document.querySelector(spotlight.targetSelector)
  if (!el) {
    rect.value = null
    return
  }
  const r = el.getBoundingClientRect()
  rect.value = { top: r.top, left: r.left, width: r.width, height: r.height }
  raf = requestAnimationFrame(update)
}

watch(
  () => spotlight.targetSelector,
  async (sel) => {
    cancelAnimationFrame(raf)
    if (!sel) {
      rect.value = null
      return
    }
    await nextTick()
    const el = document.querySelector(sel)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    raf = requestAnimationFrame(update)
  }
)

onUnmounted(() => cancelAnimationFrame(raf))
</script>

<template>
  <Teleport to="body">
    <div v-if="rect" class="spotlight-ring" :style="{
      top: rect.top - 6 + 'px',
      left: rect.left - 6 + 'px',
      width: rect.width + 12 + 'px',
      height: rect.height + 12 + 'px'
    }" @click="spotlight.hide()" />
  </Teleport>
</template>

<style scoped>
.spotlight-ring {
  position: fixed;
  border: 2px solid #00c2ff;
  border-radius: 12px;
  box-shadow: 0 0 0 4000px rgba(6, 11, 20, 0.55), 0 0 16px rgba(0, 194, 255, 0.8);
  pointer-events: none;
  z-index: 3000;
  animation: spotlight-pulse 1.2s ease-in-out infinite;
  transition: top 0.2s ease, left 0.2s ease, width 0.2s ease, height 0.2s ease;
}

@keyframes spotlight-pulse {
  0%, 100% {
    border-color: #00c2ff;
  }
  50% {
    border-color: #00e0a0;
  }
}
</style>
