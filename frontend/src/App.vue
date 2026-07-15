<script setup lang="ts">
import AppHeader from './components/AppHeader.vue'
import AppFooter from './components/AppFooter.vue'
import WaveField from './components/WaveField.vue'
import BrandShipScene from './components/BrandShipScene.vue'
import GlowFilterDefs from './components/GlowFilterDefs.vue'
import VoiceBotOverlay from './components/chat/VoiceBotOverlay.vue'
import { useChatHotkey } from '@/composables/useChatHotkey'
import { dataSourceDebugEnabled } from '@/composables/useDataSourceDebug'

useChatHotkey()
</script>

<template>
  <!-- Layer 0: ocean waves, Layer 1: ship -->
  <WaveField />
  <BrandShipScene />
  <!-- Shared SVG filter used by the map hover glow-border effect -->
  <GlowFilterDefs />

  <div
    v-if="dataSourceDebugEnabled"
    class="fixed top-0 left-0 right-0 z-[999] text-center py-1 font-mono text-[11px] tracking-wide"
    style="background: var(--color-signal-red); color: #fff"
  >
    🔍 DATA-SOURCE DEBUG MODE — 每個區塊右上角徽章顯示對接狀態，滑鼠移上去看詳細對應關係（VITE_DEBUG_DATA_SOURCE=false 可關閉）
  </div>

  <div class="content-layer min-h-screen flex flex-col" :class="{ 'pt-[26px]': dataSourceDebugEnabled }">
    <AppHeader />
    <main class="flex-1">
      <RouterView />
    </main>
    <AppFooter />
  </div>

  <!-- Second, equal interaction mode (design_docs/3) — a callable full-screen
       overlay, not a docked chat widget, so switching modes reads as
       switching the operating surface rather than opening a tool. -->
  <VoiceBotOverlay />
</template>
