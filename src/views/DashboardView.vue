<script setup lang="ts">
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import { useFleetStore } from '@/stores/fleetStore'
import { computeDailyFoc } from '@/data/mockFleet'
import { predictMaintenanceWindow } from '@/utils/predictiveMaintenance'
import { buildFleetReport, fleetReportToMarkdown } from '@/utils/reportGenerator'
import StatCard from '@/components/common/StatCard.vue'
import IsoBadge from '@/components/common/IsoBadge.vue'
import ReportDialog from '@/components/report/ReportDialog.vue'
import ShipDetailDrawer from '@/components/fleet/ShipDetailDrawer.vue'

const fleet = useFleetStore()

const reportOpen = ref(false)
const reportMarkdown = computed(() => fleetReportToMarkdown(buildFleetReport(fleet.vessels)))

const avgDailyFoc = computed(() => {
  const total = fleet.vessels.reduce((s, v) => s + computeDailyFoc(v.noon_reports[v.noon_reports.length - 1]), 0)
  return (total / fleet.vessels.length).toFixed(0)
})

const barOption = computed(() => ({
  grid: { left: 40, right: 16, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: fleet.vessels.map((v) => v.name), axisLine: { lineStyle: { color: '#5a7a9a' } } },
  yAxis: { type: 'value', name: 'Speed Loss %', splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
  tooltip: { trigger: 'axis' },
  series: [
    {
      type: 'bar',
      data: fleet.vessels.map((v) => ({
        value: v.speed_loss_pct,
        itemStyle: { color: v.status === 'critical' ? '#ff5470' : v.status === 'warning' ? '#ffb020' : '#00e0a0' }
      })),
      barWidth: '40%',
      itemStyle: { borderRadius: [6, 6, 0, 0] }
    }
  ]
}))

const rows = computed(() =>
  fleet.vessels.map((v) => ({ vessel: v, prediction: predictMaintenanceWindow(v) }))
)

const statusLabel = (status: string) => (status === 'critical' ? '高風險' : status === 'warning' ? '警示' : '正常')
const statusColor = (status: string) => (status === 'critical' ? 'error' : status === 'warning' ? 'warning' : 'secondary')
</script>

<template>
  <div class="pa-6">
    <div class="d-flex flex-wrap align-start justify-space-between ga-4 mb-4">
      <div>
        <div class="text-overline text-medium-emphasis">陽明海運 · YANG MING MARINE TRANSPORT</div>
        <div class="text-h6 font-weight-bold">節能決策儀表板</div>
      </div>
      <div class="d-flex align-center flex-wrap ga-3">
        <IsoBadge />
        <v-btn color="primary" prepend-icon="mdi-file-chart-outline" @click="reportOpen = true" data-tour="generate-report">
          生成節能分析報告
        </v-btn>
      </div>
    </div>

    <div class="d-flex flex-wrap ga-4 mb-4">
      <div style="flex: 1; min-width: 200px">
        <StatCard icon="mdi-ferry" label="船隊總數" :value="fleet.vessels.length" suffix="艘" />
      </div>
      <div style="flex: 1; min-width: 200px">
        <StatCard icon="mdi-gas-station-outline" label="平均 Daily FOC" :value="avgDailyFoc" suffix="t/day" color="warning" hint="依 ME_FULLSPEED_CONSUMP_VLSFO 公式計算" />
      </div>
      <div style="flex: 1; min-width: 200px">
        <StatCard icon="mdi-wrench-outline" label="待安排水下清潔" :value="fleet.vessels.filter(v => v.status !== 'normal').length" suffix="艘" color="error" />
      </div>
      <div style="flex: 1; min-width: 200px">
        <StatCard icon="mdi-leaf" label="節能建議產出" value="4" suffix="份" color="secondary" hint="本週 AI 自動產出" />
      </div>
    </div>

    <v-sheet rounded color="card" class="pa-4 mb-4" elevation="0">
      <div class="text-subtitle-2 mb-2">各船 Speed Loss 比較</div>
      <VChart :option="barOption" autoresize style="height: 280px" />
    </v-sheet>

    <v-sheet rounded color="card" class="pa-4" elevation="0">
      <div class="text-subtitle-2 mb-2">船隊狀態列表</div>
      <v-table density="comfortable">
        <thead>
          <tr>
            <th>船名</th>
            <th>航線</th>
            <th>Speed Loss</th>
            <th>狀態</th>
            <th>建議清潔窗口</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.vessel.id" class="vessel-row" @click="fleet.selectVessel(r.vessel.id)">
            <td>{{ r.vessel.name }}</td>
            <td>{{ r.vessel.route }}</td>
            <td>{{ r.vessel.speed_loss_pct }}%</td>
            <td><v-chip size="small" :color="statusColor(r.vessel.status)" variant="tonal">{{ statusLabel(r.vessel.status) }}</v-chip></td>
            <td>
              {{ r.prediction.recommendedDate }}
              <span class="text-caption text-medium-emphasis">
                ({{ r.prediction.breached ? '已達門檻' : r.prediction.daysToBreach !== null ? `${r.prediction.daysToBreach} 天後達門檻` : '穩定' }})
              </span>
            </td>
            <td class="text-right">
              <v-icon icon="mdi-chevron-right" size="18" color="grey" />
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-sheet>

    <ReportDialog
      v-model="reportOpen"
      title="船隊節能分析報告"
      :markdown="reportMarkdown"
      filename="ym-fleet-report.md"
    />

    <ShipDetailDrawer />
  </div>
</template>

<style scoped>
.vessel-row {
  cursor: pointer;
  transition: background 0.12s ease;
}

.vessel-row:hover {
  background: rgba(255, 255, 255, 0.04);
}
</style>
