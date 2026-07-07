<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import MascotAgent from '@/components/mascot/MascotAgent.vue'
import SpotlightOverlay from '@/components/mascot/SpotlightOverlay.vue'
import MethodologyDialog from '@/components/common/MethodologyDialog.vue'

const route = useRoute()
const drawer = ref(true)
const methodologyOpen = ref(false)

const navItems = [
  { title: '船隊總覽', icon: 'mdi-map-marker-radius', to: '/overview', tour: 'nav-overview' },
  { title: '節能決策儀表板', icon: 'mdi-view-dashboard', to: '/dashboard', tour: 'nav-dashboard' },
  { title: '歷史紀錄', icon: 'mdi-history', to: '/history', tour: 'nav-history' },
  { title: '維修排程追蹤', icon: 'mdi-clipboard-check-outline', to: '/maintenance', tour: 'nav-maintenance' }
]
</script>

<template>
  <v-app>
    <v-navigation-drawer v-model="drawer" color="surface" permanent width="240">
      <div class="pa-4">
        <div class="d-flex align-center">
          <v-icon icon="mdi-ferry" color="primary" size="28" class="mr-2" />
          <div>
            <div class="text-subtitle-1 font-weight-bold">YM Fleet AI</div>
            <div class="text-caption text-medium-emphasis">節能決策支援系統</div>
          </div>
        </div>
      </div>
      <v-divider />
      <v-list nav density="comfortable">
        <v-list-item
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          :data-tour="item.tour"
          :prepend-icon="item.icon"
          :title="item.title"
          :active="route.path === item.to"
          rounded="lg"
          class="mx-2 mb-1"
        />
      </v-list>
    </v-navigation-drawer>

    <v-app-bar color="surface" flat height="56">
      <v-app-bar-nav-icon @click="drawer = !drawer" />
      <v-app-bar-title class="text-subtitle-1">{{ route.meta.title ?? 'YM Fleet AI' }}</v-app-bar-title>
      <v-spacer />
      <v-btn icon="mdi-file-certificate-outline" variant="text" size="small" class="mr-2" @click="methodologyOpen = true" title="計算方法論 / ISO 標準對照" />
      <v-chip color="secondary" variant="tonal" size="small" prepend-icon="mdi-circle-medium" class="mr-4">
        Demo Mode · 模擬座標
      </v-chip>
    </v-app-bar>

    <v-main>
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </v-main>

    <MascotAgent />
    <SpotlightOverlay />
    <MethodologyDialog v-model="methodologyOpen" />
  </v-app>
</template>

<style scoped>
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
