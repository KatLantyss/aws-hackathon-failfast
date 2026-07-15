<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import type { BackendFuelPredictionResult } from '@/services/backend'
import { predictFuelConsumption } from '@/services/backend'
import PanelTag from '@/components/PanelTag.vue'
import KpiCard from '@/components/KpiCard.vue'
import StateDisplay from '@/components/StateDisplay.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { formatUsd } from '@/utils/format'
import { useChartTheme } from '@/composables/useChartTheme'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const chart = useChartTheme()

// Baseline noon_day: the vessel's most recent day of real data, so
// days_since_hull_clean / days_since_prop_polish and every non-overridden
// feature come from the actual DynamoDB row (API.md "使用方式一：noon_day
// lookup（推薦）") instead of the endpoint's hardcoded defaults.
const baselineNoonDay = computed(() => props.vessel.dataDayMax ?? undefined)

const form = reactive({
  speedKn: Number((props.vessel.avgSpeedKn ?? 15).toFixed(1)),
  foreDraft: props.vessel.avgForeDraftM ?? 13.5,
  aftDraft: props.vessel.avgAftDraftM ?? 13.5,
  windScale: props.vessel.avgWindScale ?? 3,
  seaHeight: props.vessel.avgSeaHeightM ?? 1,
})

const result = ref<BackendFuelPredictionResult | null>(null)
const sweep = ref<{ speedKn: number; predictedMt: number }[]>([])
const status = ref<'idle' | 'loading' | 'success' | 'error'>('idle')
const errorMessage = ref<string | null>(null)

const dsForm: DataSourceInfo = {
  status: 'real',
  endpoint: 'POST /api/v1/predict/fuel-consumption',
  description: 'XGBoost v3 Hybrid 模型（600 棵樹、29 特徵），以 noon_day 為基準抓真實歷史資料，再套用下方 what-if 欄位覆蓋。',
  fields: [
    { ui: '航速 / 前吃水 / 後吃水 / 蒲福風級 / 浪高', source: 'AVG_SPEED / FORE_DRAFT / AFTER_DRAFT / WIND_SCALE / SEA_HEIGHT（override 欄位）' },
    { ui: '基準日 (noon_day)', source: 'vessel.dataDayMax（該船最新一筆日報的 Day）' },
  ],
}
const dsResult: DataSourceInfo = {
  status: 'real',
  endpoint: 'POST /api/v1/predict/fuel-consumption',
  description: '預測油耗、UWC+PP 反事實節省與航速掃描曲線皆為後端 XGBoost 模型輸出，前端只做顯示，年化節省金額直接採用後端算好的 est_annual_saving_usd。',
  fields: [
    { ui: '預測主機油耗', source: 'predicted_consumption_mt' },
    { ui: '執行 UWC+PP 可省油耗 / 節省 %', source: 'counterfactual_uwc_pp.fuel_saving_mt_per_day / saving_pct' },
    { ui: '年化節省金額估計', source: 'counterfactual_uwc_pp.est_annual_saving_usd（後端以 300 海上天/年 × $600/MT 估算）' },
    { ui: '航速 vs. 預測油耗掃描曲線', source: '前端對 AVG_SPEED 做 ±3kt 掃描，每個點各呼叫一次同一支端點' },
  ],
}

async function runPrediction() {
  status.value = 'loading'
  errorMessage.value = null
  try {
    const [primary, ...curve] = await Promise.all([
      predictFuelConsumption({
        vessel_id: props.imo,
        noon_day: baselineNoonDay.value,
        AVG_SPEED: form.speedKn,
        FORE_DRAFT: form.foreDraft,
        AFTER_DRAFT: form.aftDraft,
        WIND_SCALE: form.windScale,
        SEA_HEIGHT: form.seaHeight,
      }),
      ...[-3, -2, -1, 0, 1, 2, 3].map((delta) =>
        predictFuelConsumption({
          vessel_id: props.imo,
          noon_day: baselineNoonDay.value,
          AVG_SPEED: Math.max(6, form.speedKn + delta),
          FORE_DRAFT: form.foreDraft,
          AFTER_DRAFT: form.aftDraft,
          WIND_SCALE: form.windScale,
          SEA_HEIGHT: form.seaHeight,
        }),
      ),
    ])
    result.value = primary
    sweep.value = curve
      .map((r) => ({ speedKn: r.input_used.avg_speed_kn, predictedMt: r.predicted_consumption_mt }))
      .sort((a, b) => a.speedKn - b.speedKn)
    status.value = 'success'
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '預測失敗'
    status.value = 'error'
  }
}

watch(() => props.imo, runPrediction, { immediate: true })

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
              data: [[result.value.input_used.avg_speed_kn, result.value.predicted_consumption_mt]],
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
        <DataSourceTag :info="dsForm" />
        <PanelTag code="FUEL-P1" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70">航行條件輸入</p>
        <p v-if="baselineNoonDay != null" class="text-[11px] text-[var(--color-ink-slate)]/50">
          基準日：Day {{ baselineNoonDay }}（該船最新一筆日報，未覆蓋的欄位會用這天的真實資料）
        </p>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">航速 (kt)</span>
          <input v-model.number="form.speedKn" type="number" step="0.1" class="field font-data" />
        </label>
        <div class="grid grid-cols-2 gap-2">
          <label class="flex flex-col gap-1 text-sm">
            <span class="text-xs text-[var(--color-ink-slate)]/60">前吃水 (m)</span>
            <input v-model.number="form.foreDraft" type="number" step="0.1" class="field font-data" />
          </label>
          <label class="flex flex-col gap-1 text-sm">
            <span class="text-xs text-[var(--color-ink-slate)]/60">後吃水 (m)</span>
            <input v-model.number="form.aftDraft" type="number" step="0.1" class="field font-data" />
          </label>
        </div>
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
          模型：{{ result?.model ?? 'xgboost_v3_hybrid' }}（XGBoost，29 特徵，含船體/螺旋槳污損退化與物理油耗基線）
        </p>
      </div>

      <!-- results -->
      <div class="flex flex-col gap-4">
        <StateDisplay v-if="status === 'error'" state="error" :error-message="errorMessage" />
        <template v-else-if="result">
          <div class="relative grid grid-cols-1 md:grid-cols-3 gap-3">
            <DataSourceTag :info="dsResult" />
            <KpiCard code="FUEL-P2" label="預測主機油耗" :value="result.predicted_consumption_mt" :formatter="(n) => `${n.toFixed(2)} MT/日`" tone="amber" />
            <KpiCard
              code="FUEL-P3"
              label="執行 UWC+PP 可省油耗"
              :value="result.counterfactual_uwc_pp.fuel_saving_mt_per_day"
              :formatter="(n) => `${n.toFixed(2)} MT/日 (${result?.counterfactual_uwc_pp.saving_pct.toFixed(1)}%)`"
              tone="teal"
            />
            <KpiCard code="FUEL-P4" label="年化節省金額估計" :value="result.counterfactual_uwc_pp.est_annual_saving_usd" :formatter="formatUsd" tone="red" />
          </div>

          <div class="panel p-3">
            <PanelTag code="FUEL-P5" class="mb-2" />
            <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">
              航速 vs. 預測油耗（以目前輸入條件為基準，對 AVG_SPEED 掃描 ±3 kt）
            </p>
            <div class="h-[300px]">
              <VChart :option="sweepOption" autoresize class="h-full w-full" />
            </div>
          </div>

          <div class="panel p-4 text-sm text-[var(--color-ink-slate)]/80">
            以目前輸入條件（{{ result.input_used.avg_speed_kn.toFixed(1) }} kt、風級 {{ result.input_used.wind_scale }}、浪高 {{ result.input_used.sea_height }}m、距上次船體清洗
            {{ Math.round(result.input_used.days_since_hull_clean) }} 天、距上次螺旋槳拋光 {{ Math.round(result.input_used.days_since_prop_polish) }} 天）預測，
            主機日耗油約 <strong class="font-data">{{ result.predicted_consumption_mt.toFixed(2) }} MT</strong>。
            {{ result.counterfactual_uwc_pp.description }}：預測日耗油降為
            <strong class="font-data">{{ result.counterfactual_uwc_pp.predicted_consumption_mt.toFixed(2) }} MT</strong>，
            每日可省 <strong class="font-data text-[var(--color-fathom-teal)]">{{ result.counterfactual_uwc_pp.fuel_saving_mt_per_day.toFixed(2) }} MT</strong>
            （約 {{ result.counterfactual_uwc_pp.saving_pct.toFixed(1) }}%），後端估算年化約可節省
            <strong class="font-data text-[var(--color-signal-red)]">{{ formatUsd(result.counterfactual_uwc_pp.est_annual_saving_usd) }}</strong>
            （{{ result.counterfactual_uwc_pp.est_annual_saving_mt.toFixed(0) }} MT/年）。
          </div>
        </template>
        <StateDisplay v-else state="loading" />
      </div>
    </div>
  </div>
</template>
