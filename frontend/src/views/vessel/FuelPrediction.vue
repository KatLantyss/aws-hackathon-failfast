<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import type { BackendFuelPredictionResult } from '@/services/backend'
import { predictFuelConsumption } from '@/services/backend'
import PanelTag from '@/components/PanelTag.vue'
import KpiCard from '@/components/KpiCard.vue'
import StateDisplay from '@/components/StateDisplay.vue'
import { formatUsd } from '@/utils/format'
import { useChartTheme } from '@/composables/useChartTheme'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const chart = useChartTheme()

const form = reactive({
  speedKn: props.vessel.designSpeedKt - 1,
  draftFwd: 14,
  draftAft: 14,
  cargoOnBoard: 80000,
  windScale: 3,
  seaHeight: 1,
})

const result = ref<BackendFuelPredictionResult | null>(null)
const sweep = ref<{ speedKn: number; predictedMt: number }[]>([])
const status = ref<'idle' | 'loading' | 'success' | 'error'>('idle')
const errorMessage = ref<string | null>(null)

const fuelPriceUsdPerMt = 620

async function runPrediction() {
  status.value = 'loading'
  errorMessage.value = null
  try {
    const [primary, ...curve] = await Promise.all([
      predictFuelConsumption({
        vessel_id: props.imo,
        speed_kn: form.speedKn,
        draft_fwd: form.draftFwd,
        draft_aft: form.draftAft,
        cargo_on_board: form.cargoOnBoard,
        wind_scale: form.windScale,
        sea_height: form.seaHeight,
      }),
      ...[-3, -2, -1, 0, 1, 2, 3].map((delta) =>
        predictFuelConsumption({
          vessel_id: props.imo,
          speed_kn: Math.max(6, form.speedKn + delta),
          draft_fwd: form.draftFwd,
          draft_aft: form.draftAft,
          cargo_on_board: form.cargoOnBoard,
          wind_scale: form.windScale,
          sea_height: form.seaHeight,
        }),
      ),
    ])
    result.value = primary
    sweep.value = curve
      .map((r) => ({ speedKn: r.input.speed_kn, predictedMt: r.predicted_consumption_mt }))
      .sort((a, b) => a.speedKn - b.speedKn)
    status.value = 'success'
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '預測失敗'
    status.value = 'error'
  }
}

watch(() => props.imo, runPrediction, { immediate: true })

const annualSavingUsd = computed(() => {
  if (!result.value) return 0
  return Math.round(result.value.counterfactual.fuel_saving_mt * fuelPriceUsdPerMt * 365)
})

const sweepOption = computed(() => {
  const c = chart.value
  return {
    animation: false,
    grid: { left: 56, right: 24, top: 24, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (p: any) => `${p[0].value[0].toFixed(1)} kt<br/>${p[0].value[1].toFixed(2)} MT/日`,
    },
    xAxis: {
      type: 'value',
      name: '航速 (kt)',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      name: 'MT/日',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: '預測油耗',
        type: 'line',
        showSymbol: true,
        symbolSize: 6,
        smooth: true,
        lineStyle: { color: c.brassAmber, width: 2 },
        itemStyle: { color: c.brassAmber },
        data: sweep.value.map((p) => [p.speedKn, p.predictedMt]),
      },
      ...(result.value
        ? [
            {
              name: '目前輸入',
              type: 'scatter' as const,
              symbolSize: 12,
              itemStyle: { color: c.signalRed },
              data: [[result.value.input.speed_kn, result.value.predicted_consumption_mt]],
            },
          ]
        : []),
    ],
  }
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-4">
      <!-- input form -->
      <div class="panel p-4 flex flex-col gap-3">
        <PanelTag code="FUEL-P1" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70">航行條件輸入</p>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">航速 (kt)</span>
          <input v-model.number="form.speedKn" type="number" step="0.1" class="field font-data" />
        </label>
        <div class="grid grid-cols-2 gap-2">
          <label class="flex flex-col gap-1 text-sm">
            <span class="text-xs text-[var(--color-ink-slate)]/60">前吃水 (m)</span>
            <input v-model.number="form.draftFwd" type="number" step="0.1" class="field font-data" />
          </label>
          <label class="flex flex-col gap-1 text-sm">
            <span class="text-xs text-[var(--color-ink-slate)]/60">後吃水 (m)</span>
            <input v-model.number="form.draftAft" type="number" step="0.1" class="field font-data" />
          </label>
        </div>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">貨載量 (MT)</span>
          <input v-model.number="form.cargoOnBoard" type="number" step="1000" class="field font-data" />
        </label>
        <div class="grid grid-cols-2 gap-2">
          <label class="flex flex-col gap-1 text-sm">
            <span class="text-xs text-[var(--color-ink-slate)]/60">蒲福風級</span>
            <input v-model.number="form.windScale" type="number" min="0" max="12" class="field font-data" />
          </label>
          <label class="flex flex-col gap-1 text-sm">
            <span class="text-xs text-[var(--color-ink-slate)]/60">浪高 (m)</span>
            <input v-model.number="form.seaHeight" type="number" step="0.1" class="field font-data" />
          </label>
        </div>
        <button
          class="mt-1 border rounded-[2px] px-3 py-2 text-xs font-display uppercase tracking-wide bg-[var(--color-brass-amber)] text-white border-[var(--color-brass-amber)] hover:opacity-90 transition-opacity disabled:opacity-40"
          :disabled="status === 'loading'"
          @click="runPrediction"
        >
          {{ status === 'loading' ? '預測中…' : '重新預測' }}
        </button>
        <p class="text-[11px] text-[var(--color-ink-slate)]/50">
          模型：{{ result?.model ?? 'cubic_speed_lsq' }}（以本船歷史 SPEED_THROUGH_WATER / ME_CONSUMPTION 最小平方擬合，加海況修正項）
        </p>
      </div>

      <!-- results -->
      <div class="flex flex-col gap-4">
        <StateDisplay v-if="status === 'error'" state="error" :error-message="errorMessage" />
        <template v-else-if="result">
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <KpiCard code="FUEL-P2" label="預測主機油耗" :value="result.predicted_consumption_mt" :formatter="(n) => `${n.toFixed(2)} MT/日`" tone="amber" />
            <KpiCard
              code="FUEL-P3"
              label="降速 1kt 可省油耗"
              :value="result.counterfactual.fuel_saving_mt"
              :formatter="(n) => `${n.toFixed(2)} MT/日 (${result!.counterfactual.saving_pct.toFixed(1)}%)`"
              tone="teal"
            />
            <KpiCard code="FUEL-P4" label="年化節省金額估計" :value="annualSavingUsd" :formatter="formatUsd" tone="red" />
          </div>

          <div class="panel p-3">
            <PanelTag code="FUEL-P5" class="mb-2" />
            <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">
              航速 vs. 預測油耗（反事實推論：以目前輸入條件為基準，掃描 ±3 kt）
            </p>
            <div class="h-[300px]">
              <VChart :option="sweepOption" autoresize class="h-full w-full" />
            </div>
          </div>

          <div class="panel p-4 text-sm text-[var(--color-ink-slate)]/80">
            以目前輸入條件（{{ result.input.speed_kn.toFixed(1) }} kt、風級 {{ result.input.wind_scale }}、浪高 {{ result.input.sea_height }}m）預測，
            主機日耗油約 <strong class="font-data">{{ result.predicted_consumption_mt.toFixed(2) }} MT</strong>。
            若降速至 <strong class="font-data">{{ result.counterfactual.slow_by_1kn_speed.toFixed(1) }} kt</strong>，
            預測日耗油降為 <strong class="font-data">{{ result.counterfactual.predicted_consumption_mt.toFixed(2) }} MT</strong>，
            每日可省 <strong class="font-data text-[var(--color-fathom-teal)]">{{ result.counterfactual.fuel_saving_mt.toFixed(2) }} MT</strong>
            （約 {{ result.counterfactual.saving_pct.toFixed(1) }}%），以燃油單價 ${{ fuelPriceUsdPerMt }}/MT 估算，年化約可節省
            <strong class="font-data text-[var(--color-signal-red)]">{{ formatUsd(annualSavingUsd) }}</strong>。
          </div>
        </template>
        <StateDisplay v-else state="loading" />
      </div>
    </div>
  </div>
</template>
