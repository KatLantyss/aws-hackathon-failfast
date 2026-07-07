import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    {
      path: '/overview',
      name: 'overview',
      component: () => import('@/views/OverviewMap.vue'),
      meta: { title: '船隊總覽', icon: 'mdi-map-marker-radius' }
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { title: '節能決策儀表板', icon: 'mdi-view-dashboard' }
    },
    {
      path: '/history',
      name: 'history',
      component: () => import('@/views/HistoryView.vue'),
      meta: { title: '歷史紀錄', icon: 'mdi-history' }
    },
    {
      path: '/maintenance',
      name: 'maintenance',
      component: () => import('@/views/MaintenanceRequestsView.vue'),
      meta: { title: '維修排程追蹤', icon: 'mdi-clipboard-check-outline' }
    }
  ]
})

export default router
