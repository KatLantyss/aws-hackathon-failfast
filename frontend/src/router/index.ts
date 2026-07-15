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
          path: 'hull-efficiency',
          name: 'vessel-hull-efficiency',
          component: () => import('@/views/vessel/HullEfficiencyDashboard.vue'),
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
          path: 'maintenance-decision',
          name: 'vessel-maintenance-decision',
          component: () => import('@/views/vessel/MaintenanceDecision.vue'),
          props: true,
        },
        {
          path: 'maintenance-correlation',
          name: 'vessel-maintenance-correlation',
          component: () => import('@/views/vessel/MaintenanceCorrelation.vue'),
          props: true,
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

export default router
