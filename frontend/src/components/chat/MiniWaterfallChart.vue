<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { FuelAttributionResponse } from '@/types/fleet'
import { useChartTheme } from '@/composables/useChartTheme'
import { useFuelWaterfallOption } from '@/composables/useFuelWaterfallOption'

const props = defineProps<{ data: FuelAttributionResponse }>()

const chart = useChartTheme()
const data = computed(() => props.data)
const option = useFuelWaterfallOption(data, chart, { compact: true })
</script>

<template>
  <div class="h-[160px]">
    <VChart :option="option" autoresize class="h-full w-full" />
  </div>
</template>
