<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { SpeedLossSeries } from '@/types/fleet'
import { useChartTheme } from '@/composables/useChartTheme'
import { useSpeedLossChart } from '@/composables/useSpeedLossChart'

const props = defineProps<{ series: SpeedLossSeries }>()

const chart = useChartTheme()
const reports = computed(() => props.series.reports)
const events = computed(() => props.series.events)
const option = useSpeedLossChart(reports, events, chart)
</script>

<template>
  <div class="h-[140px]">
    <VChart :option="option" autoresize class="h-full w-full" />
  </div>
</template>
