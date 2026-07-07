<script setup lang="ts">
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import { useFleetStore } from '@/stores/fleetStore'
import { computeDailyFoc } from '@/data/mockFleet'
import { predictMaintenanceWindow, SPEED_LOSS_THRESHOLD_PCT } from '@/utils/predictiveMaintenance'
import { vesselReportToMarkdown } from '@/utils/reportGenerator'
import StatCard from '@/components/common/StatCard.vue'
import ReportDialog from '@/components/report/ReportDialog.vue'
import MaintenanceRequestDialog from '@/components/maintenance/MaintenanceRequestDialog.vue'

const fleet = useFleetStore()

const reportOpen = ref(false)
const requestOpen = ref(false)
const reportMarkdown = computed(() => (vessel.value ? vesselReportToMarkdown(vessel.value) : ''))

const vessel = computed(() => fleet.selectedVessel)

const statusMeta = computed(() => {
  const status = vessel.value?.status
  if (status === 'critical') return { text: '高風險 · 建議安排水下清潔', color: 'error' }
  if (status === 'warning') return { text: '效能警示 · 持續觀察', color: 'warning' }
  return { text: '運作正常', color: 'secondary' }
})

const latestDailyFoc = computed(() => {
  const reports = vessel.value?.noon_reports
  if (!reports?.length) return 0
  return Number(computeDailyFoc(reports[reports.length - 1]).toFixed(1))
})

const prediction = computed(() => (vessel.value ? predictMaintenanceWindow(vessel.value) : null))

const trendOption = computed(() => {
  const reports = vessel.value?.noon_reports ?? []
  const days = reports.map((r) => r.date.slice(5))
  return {
    grid: { left: 36, right: 36, top: 20, bottom: 24 },
    xAxis: { type: 'category', data: days, axisLine: { lineStyle: { color: '#5a7a9a' } } },
    yAxis: [
      { type: 'value', name: 'Speed Loss %', axisLine: { show: false }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
      { type: 'value', name: 'Daily FOC (t)', axisLine: { show: false }, splitLine: { show: false } }
    ],
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#9fb4cc' }, top: 0, right: 0 },
    series: [
      {
        name: 'Speed Loss %',
        type: 'line',
        yAxisIndex: 0,
        data: reports.map((r) => r.speed_loss_pct),
        smooth: true,
        symbol: 'none',
        areaStyle: { color: 'rgba(0,194,255,0.15)' },
        lineStyle: { color: '#00c2ff', width: 2 }
      },
      {
        name: 'Daily FOC (t)',
        type: 'line',
        yAxisIndex: 1,
        data: reports.map((r) => Number(computeDailyFoc(r).toFixed(1))),
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#ffb020', width: 2, type: 'dashed' }
      }
    ]
  }
})
</script>

<template>
  <v-navigation-drawer
    :model-value="fleet.detailOpen"
    location="right"
    temporary
    width="420"
    color="surface"
    @update:model-value="(val: boolean) => !val && fleet.closeDetail()"
  >
    <template v-if="vessel">
      <div class="pa-4">
        <div class="d-flex align-center justify-space-between mb-1">
          <div class="d-flex align-center ga-2">
            <v-icon icon="mdi-ferry" color="primary" />
            <span class="text-h6">{{ vessel.name }}</span>
          </div>
          <v-btn icon="mdi-close" variant="text" size="small" @click="fleet.closeDetail" />
        </div>
        <div class="text-caption text-medium-emphasis mb-1">{{ vessel.type }}</div>
        <div class="d-flex align-center justify-space-between">
          <v-chip size="small" :color="statusMeta.color" variant="tonal">{{ statusMeta.text }}</v-chip>
          <v-btn size="small" variant="text" prepend-icon="mdi-file-chart-outline" data-tour="vessel-report" @click="reportOpen = true">
            產出本船報告
          </v-btn>
        </div>

        <v-divider class="my-4" />

        <div class="text-caption text-medium-emphasis mb-2">目前航線</div>
        <div class="d-flex align-center ga-2 mb-4">
          <v-icon icon="mdi-map-marker-path" size="18" color="primary" />
          <span class="text-body-2">{{ vessel.route }}</span>
        </div>

        <div class="d-flex flex-wrap ga-3 mb-4">
          <div style="flex: 1; min-width: 150px">
            <StatCard icon="mdi-speedometer" label="航速" :value="vessel.speed_knots" suffix="knots" />
          </div>
          <div style="flex: 1; min-width: 150px">
            <StatCard icon="mdi-gas-station-outline" label="Daily FOC" :value="latestDailyFoc" suffix="t/day" hint="依 ME_FULLSPEED_CONSUMP_VLSFO 公式計算" />
          </div>
        </div>

        <v-sheet rounded color="card" class="pa-3 mb-4" elevation="0">
          <div class="text-caption text-medium-emphasis mb-2">Speed Loss / Daily FOC 趨勢 (近 14 日午報)</div>
          <VChart :option="trendOption" autoresize style="height: 200px" />
        </v-sheet>

        <v-sheet v-if="prediction" rounded color="card" class="pa-3 mb-4" elevation="0">
          <div class="d-flex align-center ga-2 mb-2">
            <v-icon icon="mdi-calendar-clock-outline" size="18" color="warning" />
            <span class="text-caption text-medium-emphasis">維修排程建議</span>
          </div>
          <div v-if="prediction.breached" class="text-body-2">
            Speed Loss 已超過 {{ SPEED_LOSS_THRESHOLD_PCT }}% 門檻，船舶無法立即離航清潔，建議於下次靠港（<strong>{{ prediction.recommendedDate }}</strong>）安排水下清潔。
          </div>
          <div v-else-if="prediction.daysToBreach !== null" class="text-body-2">
            依目前劣化速率，預計 <strong>{{ prediction.daysToBreach }} 天後</strong>達到 {{ SPEED_LOSS_THRESHOLD_PCT }}% 門檻，建議提前規劃於下次靠港（<strong>{{ prediction.recommendedDate }}</strong>）安排水下清潔。
          </div>
          <div v-else class="text-body-2">目前效能穩定，暫無需提前安排清潔。</div>
          <div class="text-caption text-medium-emphasis mt-2 mb-3">
            預估清潔後每日可減少約 <strong>{{ prediction.estFuelSavingTDay }} t</strong> 油耗
          </div>
          <v-btn
            block
            color="primary"
            prepend-icon="mdi-calendar-check-outline"
            data-tour="schedule-cleaning"
            @click="requestOpen = true"
          >
            安排水下清潔
          </v-btn>
        </v-sheet>

        <v-sheet rounded color="card" class="pa-3" elevation="0">
          <div class="text-caption text-medium-emphasis mb-2">水下清潔紀錄</div>
          <div class="d-flex justify-space-between text-body-2 mb-2">
            <span class="text-medium-emphasis">上次水下清潔</span>
            <span>{{ vessel.last_hull_clean }}</span>
          </div>
          <div class="d-flex justify-space-between text-body-2">
            <span class="text-medium-emphasis">下次水下清潔排程</span>
            <span>{{ vessel.next_hull_clean }}</span>
          </div>
        </v-sheet>
      </div>
    </template>
  </v-navigation-drawer>

  <ReportDialog
    v-model="reportOpen"
    :title="vessel ? `${vessel.name} 節能分析報告` : '節能分析報告'"
    :markdown="reportMarkdown"
    :filename="vessel ? `${vessel.id}-report.md` : 'vessel-report.md'"
  />

  <MaintenanceRequestDialog
    v-model="requestOpen"
    :vessel="vessel"
    :default-date="prediction?.recommendedDate ?? ''"
  />
</template>
