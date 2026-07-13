<script setup lang="ts">
import AppHeader from './components/AppHeader.vue'
import AppFooter from './components/AppFooter.vue'
import WaveField from './components/WaveField.vue'
import BrandShipScene from './components/BrandShipScene.vue'
import GlowFilterDefs from './components/GlowFilterDefs.vue'
import VoiceBotOverlay from './components/chat/VoiceBotOverlay.vue'
import { useChatHotkey } from '@/composables/useChatHotkey'

useChatHotkey()
</script>

<template>
  <!-- Layer 0: ocean waves, Layer 1: ship -->
  <WaveField />
  <BrandShipScene />
  <!-- Shared SVG filter used by the map hover glow-border effect -->
  <GlowFilterDefs />

  <div class="content-layer min-h-screen flex flex-col">
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
