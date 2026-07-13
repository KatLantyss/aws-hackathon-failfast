<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { SpeedLossSeries, VesselSummary } from '@/types/fleet'
import FathometerGauge from '@/components/FathometerGauge.vue'
import { useChartTheme } from '@/composables/useChartTheme'

const props = defineProps<{
  a: { vessel: VesselSummary; series: SpeedLossSeries }
  b: { vessel: VesselSummary; series: SpeedLossSeries }
}>()

const chart = useChartTheme()

const option = computed(() => {
  const c = chart.value
  return {
    animation: false,
    grid: { left: 36, right: 12, top: 28, bottom: 24 },
    legend: { top: 0, textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 10, color: c.inkSlate } },
    tooltip: { trigger: 'axis', backgroundColor: c.marineNavy, textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 11 } },
    xAxis: { type: 'time', axisLabel: { show: false }, splitLine: { show: false } },
    yAxis: {
      type: 'value',
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 9, color: c.inkSlate, formatter: '{value}%' },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: props.a.vessel.name,
        type: 'line',
        showSymbol: false,
        lineStyle: { color: c.brassAmber, width: 1.5 },
        data: props.a.series.reports.map((r) => [r.date, r.speedLossPct]),
      },
      {
        name: props.b.vessel.name,
        type: 'line',
        showSymbol: false,
        lineStyle: { color: c.fathomTeal, width: 1.5 },
        data: props.b.series.reports.map((r) => [r.date, r.speedLossPct]),
      },
    ],
  }
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex items-center justify-around gap-4">
      <FathometerGauge
        size="sm"
        :value="Math.min(100, a.vessel.speedLossPct * 8)"
        :grade="a.vessel.foulingGrade"
        :label="a.vessel.name"
        :display-value="`${a.vessel.speedLossPct.toFixed(1)}%`"
      />
      <FathometerGauge
        size="sm"
        :value="Math.min(100, b.vessel.speedLossPct * 8)"
        :grade="b.vessel.foulingGrade"
        :label="b.vessel.name"
        :display-value="`${b.vessel.speedLossPct.toFixed(1)}%`"
      />
    </div>
    <div class="h-[140px]">
      <VChart :option="option" autoresize class="h-full w-full" />
    </div>
  </div>
</template>
