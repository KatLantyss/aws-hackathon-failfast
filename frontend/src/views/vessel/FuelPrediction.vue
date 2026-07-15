<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import type { BackendFuelPredictionResult, BackendNoonReport } from '@/services/backend'
import { getNoonReports, getSpeedLoss, predictFuelConsumption } from '@/services/backend'
import KpiCard from '@/components/KpiCard.vue'
import StateDisplay from '@/components/StateDisplay.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { useChartTheme } from '@/composables/useChartTheme'

const formatUsd = (value: number) => new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
}).format(value)

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const chart = useChartTheme()

// v5 can only serve steady-state reports (wind <= 4 and full-speed >= 22h).
// Resolve the newest eligible report per vessel, rather than blindly using its
// latest report or replacing that report's weather with fleet-wide averages.
const baselineNoonDay = ref<number | null>(null)
const baselineReport = ref<BackendNoonReport | null>(null)

const form = reactive({
  speedKn: Number((props.vessel.avgSpeedKn ?? 15).toFixed(1)),
  foreDraft: props.vessel.avgForeDraftM ?? 13.5,
  aftDraft: props.vessel.avgAftDraftM ?? 13.5,
  windScale: props.vessel.avgWindScale ?? 3,
  seaHeight: props.vessel.avgSeaHeightM ?? 1,
})

const result = ref<BackendFuelPredictionResult | null>(null)
const sweep = ref<{ speedKn: number; predictedMt: number }[]>([])
const sweepUnavailable = ref(false)
const status = ref<'idle' | 'loading' | 'success' | 'error'>('idle')
const errorMessage = ref<string | null>(null)

const v5CalibrationValidated = false

const dsForm: DataSourceInfo = {
  status: 'real',
  endpoint: 'POST /api/v1/predict/fuel-consumption',
  description: 'v5 XGBoost + LightGBM 50:50 ensemble（30 特徵）；畫面 MT 輸出已換回 NOON Report 的來源燃油全速時段量，並保留 VLSFO 等效 24 小時值供稽核。僅適用於風級 ≤4、全速航行 ≥22 小時的穩態日報。',
  fields: [
    { ui: '航速 / 前吃水 / 後吃水 / 蒲福風級 / 浪高', source: 'AVG_SPEED / FORE_DRAFT / AFTER_DRAFT / WIND_SCALE / SEA_HEIGHT（override 欄位）' },
    { ui: '基準日 (noon_day)', source: '自動選取該船最近一筆風級 ≤4 且全速航行 ≥22 小時的 NOON Report' },
  ],
}
const dsResult: DataSourceInfo = {
  status: 'real',
  endpoint: 'POST /api/v1/predict/fuel-consumption',
  description: 'v5 以穩態 NOON Report 為基準，固定船況、海況與維修狀態後，輸出受控情境的油耗與成本差額估計；成本以中油牌價代理並按公開 USD/TWD 匯率統一換算美元，不作完整財務 ROI 預報。',
  fields: [
    { ui: '基準情境性能估計', source: 'predicted_consumption_mt（NOON Report 來源燃油的全速時段 MT）' },
    { ui: '清潔情境模型差值', source: 'counterfactual_uwc_pp（維修年齡與 FOC speed loss 歸零的反事實輸出）' },
    { ui: '年度燃油成本差額（USD）', source: 'counterfactual_uwc_pp.energy_pricing.annual_saving_usd（中油柴油公開牌價 × 公開 USD/TWD 匯率）' },
  ],
}

async function loadSpeedLossFallback(vesselId: string) {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      getSpeedLoss(vesselId),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error('取得舊版 speed-loss 基準資料逾時，請稍後再試。')), 15_000)
      }),
    ])
  } finally {
    if (timer) clearTimeout(timer)
  }
}

async function selectBaseline(vesselId: string) {
  const reports = await getNoonReports(vesselId)
  let hoursByNoonDay = new Map<number, number>()

  // Newer APIs include HOURS_FULL_SPEED in noon reports. Avoid an expensive
  // speed-loss request in the normal path; only query it for old deployments.
  if (!reports.records.some((report) => report.hours_full_speed != null)) {
    const speedLoss = await loadSpeedLossFallback(vesselId)
    const speedLossRows = Array.isArray(speedLoss.slip_timeline)
      ? speedLoss.slip_timeline
      : (speedLoss as unknown as { foc_timeline?: Array<{ noon_day: number; hours_full_speed: number | null }> }).foc_timeline ?? []
    hoursByNoonDay = new Map(
      speedLossRows
        .filter((point) => point.hours_full_speed != null)
        .map((point) => [point.noon_day, point.hours_full_speed] as const),
    )
  }

  const eligible = reports.records
    .map((report) => ({
      report,
      hoursFullSpeed: report.hours_full_speed ?? hoursByNoonDay.get(report.noon_day) ?? null,
    }))
    .filter(({ report, hoursFullSpeed }) => report.noon_day != null
      && report.wind_scale != null && report.wind_scale <= 4
      && hoursFullSpeed != null && hoursFullSpeed >= 22)
    .sort((a, b) => b.report.noon_day - a.report.noon_day)[0]

  if (!eligible) {
    throw new Error('找不到符合 v5 條件（風級 ≤4、全速航行 ≥22 小時）的 NOON Report，無法進行穩態性能分析。')
  }

  const baseline = { ...eligible.report, hours_full_speed: eligible.hoursFullSpeed }
  baselineNoonDay.value = baseline.noon_day
  baselineReport.value = baseline
  form.speedKn = baseline.avg_speed_kn ?? form.speedKn
  form.foreDraft = baseline.fore_draft ?? form.foreDraft
  form.aftDraft = baseline.aft_draft ?? form.aftDraft
  form.windScale = baseline.wind_scale ?? form.windScale
  form.seaHeight = baseline.sea_height ?? form.seaHeight
}

function predictionInput(speedKn = form.speedKn) {
  return {
    vessel_id: props.imo,
    noon_day: baselineNoonDay.value ?? undefined,
    AVG_SPEED: speedKn,
    FORE_DRAFT: form.foreDraft,
    AFTER_DRAFT: form.aftDraft,
    WIND_SCALE: form.windScale,
    SEA_HEIGHT: form.seaHeight,
  }
}

async function runPrediction() {
  if (baselineNoonDay.value == null) {
    status.value = 'error'
    errorMessage.value = '尚未取得可用的 v5 基準日。'
    return
  }
  if (form.windScale > 4) {
    status.value = 'error'
    errorMessage.value = 'v5 僅適用於蒲福風級 ≤4。請將風級調整為 4 以下後再預測。'
    return
  }

  status.value = 'loading'
  errorMessage.value = null
  sweepUnavailable.value = false
  try {
    // The primary value is authoritative. A failed chart point must not hide it.
    const primary = await predictFuelConsumption(predictionInput())
    result.value = primary

    const curveResults = await Promise.allSettled(
      [-3, -2, -1, 0, 1, 2, 3].map((delta) =>
        predictFuelConsumption(predictionInput(Math.max(6, form.speedKn + delta))),
      ),
    )
    const fulfilled = curveResults
      .filter((outcome): outcome is PromiseFulfilledResult<BackendFuelPredictionResult> => outcome.status === 'fulfilled')
      .map((outcome) => outcome.value)
    sweep.value = fulfilled
      .map((item) => ({ speedKn: item.input_used.avg_speed_kn, predictedMt: item.predicted_consumption_mt }))
      .sort((a, b) => a.speedKn - b.speedKn)
    sweepUnavailable.value = fulfilled.length !== curveResults.length
    status.value = 'success'
  } catch (e) {
    result.value = null
    sweep.value = []
    errorMessage.value = e instanceof Error ? e.message : '預測失敗'
    status.value = 'error'
  }
}

async function loadVesselPrediction() {
  status.value = 'loading'
  errorMessage.value = null
  result.value = null
  sweep.value = []
  baselineNoonDay.value = null
  baselineReport.value = null
  try {
    await selectBaseline(props.imo)
    await runPrediction()
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : '無法取得 v5 預測基準日'
    status.value = 'error'
  }
}

watch(() => props.imo, () => { void loadVesselPrediction() }, { immediate: true })

const sweepOption = computed(() => {
  const c = chart.value
  return {
    animation: false,
    grid: { left: 56, right: 24, top: 24, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (p: any) => `${p[0].value[0].toFixed(1)} kt<br/>${p[0].value[1].toFixed(2)} MT（NOON 全速時段）`,
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
      name: 'MT（NOON 全速時段）',
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
      <div class="panel p-4 flex flex-col gap-3">
        <DataSourceTag :info="dsForm" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70">受控航行情境</p>
        <p v-if="baselineNoonDay != null" class="text-[11px] text-[var(--color-ink-slate)]/50">
          比較基準：Day {{ baselineNoonDay }}（穩態日報；風級 {{ baselineReport?.wind_scale }}、全速 {{ baselineReport?.hours_full_speed }} 小時）
        </p>
        <label class="flex flex-col gap-1 text-sm"><span class="text-xs text-[var(--color-ink-slate)]/60">比較航速 (kt)</span><input v-model.number="form.speedKn" type="number" step="0.1" class="field font-data" /></label>
        <div class="grid grid-cols-2 gap-2">
          <label class="flex flex-col gap-1 text-sm"><span class="text-xs text-[var(--color-ink-slate)]/60">前吃水 (m)</span><input v-model.number="form.foreDraft" type="number" step="0.1" class="field font-data" /></label>
          <label class="flex flex-col gap-1 text-sm"><span class="text-xs text-[var(--color-ink-slate)]/60">後吃水 (m)</span><input v-model.number="form.aftDraft" type="number" step="0.1" class="field font-data" /></label>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <label class="flex flex-col gap-1 text-sm"><span class="text-xs text-[var(--color-ink-slate)]/60">蒲福風級（≤4）</span><input v-model.number="form.windScale" type="number" min="0" max="4" class="field font-data" /></label>
          <label class="flex flex-col gap-1 text-sm"><span class="text-xs text-[var(--color-ink-slate)]/60">浪高 (m)</span><input v-model.number="form.seaHeight" type="number" step="0.1" class="field font-data" /></label>
        </div>
        <button class="mt-1 border rounded-[2px] px-3 py-2 text-xs font-display uppercase tracking-wide bg-[var(--color-brass-amber)] text-white border-[var(--color-brass-amber)] hover:opacity-90 transition-opacity disabled:opacity-40" :disabled="status === 'loading'" @click="runPrediction">
          {{ status === 'loading' ? '計算中…' : '重新計算情境' }}
        </button>
        <p class="text-[11px] text-[var(--color-ink-slate)]/50">固定本頁條件後比較模型輸出，供判讀船體性能與維修狀態；不是未來日油耗預報，也不等同任一 NOON Report 的實測日耗。</p>
      </div>

      <div class="flex flex-col gap-4">
        <StateDisplay v-if="status === 'error'" state="error" :error-message="errorMessage" />
        <template v-else-if="result">
          <div class="panel p-4 border-l-4 border-[var(--color-fathom-teal)]">
            <p class="font-display text-sm tracking-wide text-[var(--color-fathom-teal)]">穩態船體性能分析</p>
            <p class="mt-1 text-sm text-[var(--color-ink-slate)]/75">固定船況、海況與全速航行條件後，使用模型比較目前維修狀態與理想清潔狀態。這是控制條件下的相對性能工具，不預報下一天的燃油消耗。</p>
          </div>
          <div class="relative grid grid-cols-1 md:grid-cols-3 gap-3">
            <DataSourceTag :info="dsResult" />
            <KpiCard code="FUEL-P2" label="基準情境性能估計" :value="result.predicted_consumption_mt" :formatter="(n) => `${n.toFixed(2)} MT`" tone="amber" />
            <KpiCard
              code="FUEL-P3"
              label="清潔情境模型差值（校準中）"
              :value="result.counterfactual_uwc_pp.raw_fuel_delta_mt_per_day"
              :formatter="(n) => `${n.toFixed(2)} MT`"
              tone="teal"
            />
            <KpiCard code="FUEL-P4" label="年度燃油成本差額（USD，模型估計）" :value="result.counterfactual_uwc_pp.energy_pricing.annual_saving_usd" :formatter="(n) => result?.counterfactual_uwc_pp.benefit_available ? formatUsd(n) : '無正向差額'" tone="red" />
          </div>
          <p class="text-xs text-[var(--color-ink-slate)]/55">
            清潔情境模型差值：目前狀態 vs. 假設完成 UWC+PP；屬模型輸出，非保證節省。
          </p>

          <div class="panel p-3">
            <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">航速 vs. 預測油耗（NOON Report 來源燃油的全速時段量；以目前輸入條件為基準，對 AVG_SPEED 掃描 ±3 kt）</p>
            <div v-if="sweep.length" class="h-[300px]"><VChart :option="sweepOption" autoresize class="h-full w-full" /></div>
            <p v-else class="py-12 text-center text-sm text-[var(--color-ink-slate)]/55">航速掃描目前沒有可顯示的預測點。</p>
            <p v-if="sweepUnavailable" class="mt-2 text-xs text-[var(--color-ink-slate)]/55">部分掃描點無法取得；主預測值仍以成功回應顯示。</p>
          </div>

          <div class="panel p-4 text-sm text-[var(--color-ink-slate)]/80">
            <p><strong>本次固定條件：</strong>{{ result.input_used.avg_speed_kn.toFixed(1) }} kt、風級 {{ result.input_used.wind_scale }}、浪高 {{ result.input_used.sea_height }}m、距上次船體清洗 {{ result.input_used.days_since_hull_clean == null ? '無紀錄' : `${Math.round(result.input_used.days_since_hull_clean)} 天` }}、距上次螺旋槳拋光 {{ result.input_used.days_since_prop_polish == null ? '無紀錄' : `${Math.round(result.input_used.days_since_prop_polish)} 天` }}。</p>
            <p class="mt-2">在這組受控條件下，模型估計全速時段的 {{ result.input_used.fuel_type === 'MIXED' ? '混合燃油' : result.input_used.fuel_type.replace('ME_FULLSPEED_CONSUMP_', '') }} 為 <strong class="font-data">{{ result.predicted_consumption_mt.toFixed(2) }} MT</strong>；清潔情境的模型輸出為 <strong class="font-data">{{ result.counterfactual_uwc_pp.predicted_consumption_mt.toFixed(2) }} MT</strong>。</p>
            <p v-if="result.counterfactual_uwc_pp.benefit_available" class="mt-2">依 {{ result.counterfactual_uwc_pp.energy_pricing.price_source.name }} 的柴油牌價（{{ result.counterfactual_uwc_pp.energy_pricing.price_twd_per_litre.toFixed(1) }} TWD/L）與 USD/TWD {{ result.counterfactual_uwc_pp.energy_pricing.exchange_rate.twd_per_usd.toFixed(2) }}，模型估計燃油成本差額約為 <strong class="font-data">{{ formatUsd(result.counterfactual_uwc_pp.energy_pricing.daily_saving_usd) }}/日</strong>、<strong class="font-data">{{ formatUsd(result.counterfactual_uwc_pp.energy_pricing.annual_saving_usd) }}/年</strong>（{{ result.counterfactual_uwc_pp.energy_pricing.sea_days_per_year }} 海上天）。</p>
            <p v-else class="mt-2">此情境未產生正向模型油耗差額，因此不估列燃油成本差額。</p>
            <p class="mt-1 text-xs text-[var(--color-ink-slate)]/55">匯率來源：<a class="underline" :href="result.counterfactual_uwc_pp.energy_pricing.exchange_rate.url" target="_blank" rel="noreferrer">{{ result.counterfactual_uwc_pp.energy_pricing.exchange_rate.name }}</a>（{{ result.counterfactual_uwc_pp.energy_pricing.exchange_rate.status === 'fetched' ? '已取得公開匯率' : '使用 fallback 匯率' }}）；油價來源：<a class="underline" :href="result.counterfactual_uwc_pp.energy_pricing.price_source.url" target="_blank" rel="noreferrer">{{ result.counterfactual_uwc_pp.energy_pricing.price_source.name }}</a>。</p>
            <p class="mt-3 text-xs text-[var(--color-ink-slate)]/60">NOON Report 的每日油耗同時受實際全速時數、天候、載貨、操船、航段與量測因素影響。因此即使其他可見欄位相近，也可能出現航速提高但日油耗下降；那是日報觀測的混雜因素，不能直接解讀成航速與油耗的因果關係。</p>
            <p class="mt-2 text-xs font-medium text-[var(--color-signal-red)]/75">校準警示：跨船抽樣回測仍有顯著偏差（例如 S1 -21%、S2 -41%）。目前只用於檢視受控情境下的模型輸出；不將 UWC+PP 差值解讀為實際節省、成本效益或 ROI。</p>
          </div>
        </template>
        <StateDisplay v-else state="loading" />
      </div>
    </div>
  </div>
</template>
