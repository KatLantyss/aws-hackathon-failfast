import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'fleet-overview',
      component: () => import('@/views/FleetOverview.vue'),
    },
    {
      path: '/vessels',
      name: 'vessel-list',
      component: () => import('@/views/VesselList.vue'),
    },
    {
      path: '/vessels/:imo',
      component: () => import('@/views/VesselLayout.vue'),
      props: true,
      children: [
        { path: '', redirect: (to) => ({ path: `/vessels/${to.params.imo}/overview` }) },
        {
          path: 'overview',
          name: 'vessel-overview',
          component: () => import('@/views/vessel/VesselOverview.vue'),
          props: true,
        },
        {
          path: 'noon-reports',
          name: 'vessel-noon-reports',
          component: () => import('@/views/vessel/NoonReports.vue'),
          props: true,
        },
        {
          path: 'inspections',
          name: 'vessel-inspections',
          component: () => import('@/views/vessel/Inspections.vue'),
          props: true,
        },
        {
          path: 'speed-loss',
          name: 'vessel-speed-loss',
          component: () => import('@/views/vessel/SpeedLoss.vue'),
          props: true,
        },
        {
          path: 'fuel-attribution',
          name: 'vessel-fuel-attribution',
          component: () => import('@/views/vessel/FuelAttribution.vue'),
          props: true,
        },
        {
          path: 'maintenance-advisor',
          name: 'vessel-maintenance-advisor',
          component: () => import('@/views/vessel/MaintenanceAdvisor.vue'),
          props: true,
        },
      ],
    },
    {
      path: '/fleet-analytics',
      name: 'fleet-analytics',
      component: () => import('@/views/FleetAnalytics.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

export default router
