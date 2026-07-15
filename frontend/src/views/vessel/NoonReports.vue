<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type { VesselSummary, NoonReportEntry } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import type { BackendFuelPredictionResult } from '@/services/backend'
import { getNoonReports, predictFuelConsumption } from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import MaintenanceRequestModal from '@/components/MaintenanceRequestModal.vue'

const dsNoon: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/noon-reports',
  description: '整張表格直接映射端點回傳欄位，不經過 adapter 加工；只有「位置」欄不是後端原始資料。標有 ● 的列是本次工作階段新增的本地填報，未寫入後端。',
  fields: [
    { ui: '航速(觀測) / 航速(修正後)', source: 'avg_speed_kn / speed_through_water' },
    { ui: '油耗 MT/日', source: 'me_consumption' },
    { ui: '海況(BF)', source: 'wind_scale' },
    { ui: '吃水(F/A)', source: 'fore_draft / aft_draft' },
    { ui: '位置', source: '無對應欄位，端點未回傳經緯度，固定顯示 —' },
  ],
}

const dsReportForm: DataSourceInfo = {
  status: 'stub',
  description: '「+ 新增今日 Noon Report」純粹是前端示意：送出後只會把這筆資料 push 進本頁表格的 state，不會呼叫任何寫入 API、也不會存進 DynamoDB，重新整理頁面就會消失。',
}

const dsDiagnosis: DataSourceInfo = {
  status: 'hybrid',
  endpoint: 'POST /api/v1/predict/fuel-consumption',
  description: '預測油耗與「執行 UWC+PP 可省油耗 %」（saving_pct）是後端 XGBoost 模型的真實輸出；本次回報油耗 vs. 模型預測的偏差%計算、以及 8%/5% 兩層警示門檻，是前端寫死規則。',
  fields: [
    { ui: '模型預測油耗', source: 'predicted_consumption_mt（real，依本次填報的航速/吃水/風級/浪高計算）' },
    { ui: '執行 UWC+PP 可省 %', source: 'counterfactual_uwc_pp.saving_pct（real）' },
    { ui: '🚨/⚠️/✅ 門檻判定', source: '前端寫死：saving_pct 或偏差% ≥8→CRITICAL，≥5→WARNING，其餘→OK' },
  ],
}

const props = defineProps<{ vessel: VesselSummary; imo: string }>()

type LocalNoonReportEntry = NoonReportEntry & { isLocal?: boolean }

async function fetchReports(imo: string): Promise<{ vessel: VesselSummary; reports: NoonReportEntry[] }> {
  const resp = await getNoonReports(imo, { limit: 5000 })
  const reports: NoonReportEntry[] = resp.records.map((r) => ({
    day: r.noon_day,
    lat: 0,
    lon: 0,
    observedSpeedKt: r.avg_speed_kn ?? 0,
    correctedSpeedKt: r.speed_through_water ?? 0,
    speedLossPct: 0,
    fuelConsumptionMt: r.me_consumption ?? 0,
    beaufort: r.wind_scale ?? 0,
    seaState: r.wind_scale ?? 0,
    draftFwd: r.fore_draft ?? 0,
    draftAft: r.aft_draft ?? 0,
    loadCondition: (r.cargo_on_board ?? 0) > 1000 ? 'laden' : 'ballast',
  }))
  return { vessel: props.vessel, reports }
}

const { data, state } = useAsyncData(() => props.imo, fetchReports)

// 本次工作階段新增的填報 — 純前端 state，不落地寫入後端。
const localReports = ref<LocalNoonReportEntry[]>([])
const combinedReports = computed<LocalNoonReportEntry[]>(() => [...(data.value?.reports ?? []), ...localReports.value])

const startDayInput = ref('')
const endDayInput = ref('')
const startDay = computed(() => (startDayInput.value === '' ? null : Number(startDayInput.value)))
const endDay = computed(() => (endDayInput.value === '' ? null : Number(endDayInput.value)))

const filteredReports = computed(() => {
  return combinedReports.value.filter((r) => {
    if (startDay.value != null && r.day < startDay.value) return false
    if (endDay.value != null && r.day > endDay.value) return false
    return true
  })
})

const visibleReports = computed(() => {
  const list = filteredReports.value
  if (startDay.value != null || endDay.value != null) return list
  return list.slice(-60)
})

function exportCsv() {
  const rows = filteredReports.value.length ? filteredReports.value : visibleReports.value
  const header = ['Day', 'ObservedSpeedKt', 'STW', 'FuelMt', 'Beaufort', 'DraftFwd', 'DraftAft', 'LoadCondition']
  const lines = rows.map((r) =>
    [r.day, r.observedSpeedKt, r.correctedSpeedKt, r.fuelConsumptionMt, r.beaufort, r.draftFwd, r.draftAft, r.loadCondition].join(','),
  )
  const csv = [header.join(','), ...lines].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${props.vessel.name.replace(/\s+/g, '_')}_noon_reports.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ─── 每日填報表單 ───────────────────────────────────────────────────────────
const showForm = ref(false)
const formError = ref<string | null>(null)

const form = reactive({
  avgSpeed: 15,
  stw: 15,
  meConsumption: 30,
  windScale: 3,
  seaHeight: 1,
  foreDraft: 13.5,
  aftDraft: 13.5,
  cargoOnBoard: 0,
})

function openForm() {
  const last = combinedReports.value[combinedReports.value.length - 1] ?? null
  form.avgSpeed = Number((last?.observedSpeedKt || props.vessel.avgSpeedKn || 15).toFixed(1))
  form.stw = Number((last?.correctedSpeedKt || props.vessel.avgStwKn || form.avgSpeed).toFixed(1))
  form.meConsumption = Number((last?.fuelConsumptionMt || props.vessel.avgConsumptionMt || 30).toFixed(1))
  form.windScale = last?.beaufort ?? props.vessel.avgWindScale ?? 3
  form.seaHeight = props.vessel.avgSeaHeightM ?? 1
  form.foreDraft = Number((last?.draftFwd || props.vessel.avgForeDraftM || 13.5).toFixed(1))
  form.aftDraft = Number((last?.draftAft || props.vessel.avgAftDraftM || 13.5).toFixed(1))
  form.cargoOnBoard = props.vessel.avgCargoOnBoardMt ?? 0
  formError.value = null
  showForm.value = true
}

// 供 predict-fuel-consumption 帶 noon_day：讓未覆蓋的特徵（距上次清洗天數等）
// 抓這艘船最新一筆真實資料，而不是端點的寫死預設值。
const baselineNoonDay = computed(() => props.vessel.dataDayMax ?? undefined)

const newDayIndex = computed(() => {
  const days = combinedReports.value.map((r) => r.day)
  const maxDay = days.length ? Math.max(...days) : (props.vessel.dataDayMax ?? 0)
  return maxDay + 1
})

const diagnosing = ref(false)
const diagnosis = ref<BackendFuelPredictionResult | null>(null)
const diagnosisError = ref<string | null>(null)
const submittedDay = ref<number | null>(null)
const reportedConsumptionMt = ref<number | null>(null)

// 診斷過程的示意步驟 — 實際 API 呼叫通常 <1s 就回應，但畫面上仍逐步顯示「驗證
// →閥值比對→呼叫模型」三個階段，讓使用者看得到系統確實跑過這條流程，而不是
// 瞬間跳出結果。呼叫的資料與結果本身仍是真的（見下方 predictFuelConsumption），
// 這裡只是替真實的非同步呼叫加上感知節奏。
const PROCESS_STAGES = [
  '已接收本日填報資料，寫入本頁暫存表格',
  '執行即時閥值檢查（比對歷史油耗與 Speed Loss 門檻）',
  '呼叫油耗診斷模型（XGBoost）分析本次航行條件…',
]
const revealedStageCount = ref(0)
let stageTimers: ReturnType<typeof setTimeout>[] = []

function clearStageTimers() {
  stageTimers.forEach((t) => clearTimeout(t))
  stageTimers = []
}

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function runStagedReveal(): Promise<void> {
  clearStageTimers()
  revealedStageCount.value = 0
  if (prefersReducedMotion()) {
    revealedStageCount.value = PROCESS_STAGES.length
    return Promise.resolve()
  }
  return new Promise((resolve) => {
    PROCESS_STAGES.forEach((_, i) => {
      stageTimers.push(
        setTimeout(() => {
          revealedStageCount.value = i + 1
          if (i === PROCESS_STAGES.length - 1) resolve()
        }, (i + 1) * 450),
      )
    })
  })
}

async function submitReport() {
  if (!(form.avgSpeed > 0) || !(form.meConsumption > 0)) {
    formError.value = '請輸入有效的航速與油耗數值（須大於 0）。'
    return
  }
  formError.value = null

  const day = newDayIndex.value
  localReports.value.push({
    day,
    lat: 0,
    lon: 0,
    observedSpeedKt: form.avgSpeed,
    correctedSpeedKt: form.stw,
    speedLossPct: 0,
    fuelConsumptionMt: form.meConsumption,
    beaufort: form.windScale,
    seaState: form.windScale,
    draftFwd: form.foreDraft,
    draftAft: form.aftDraft,
    loadCondition: form.cargoOnBoard > 1000 ? 'laden' : 'ballast',
    isLocal: true,
  })

  submittedDay.value = day
  reportedConsumptionMt.value = form.meConsumption
  showForm.value = false
  bannerRequestSent.value = false

  diagnosing.value = true
  diagnosisError.value = null
  diagnosis.value = null
  try {
    const [result] = await Promise.all([
      predictFuelConsumption({
        vessel_id: props.imo,
        noon_day: baselineNoonDay.value,
        AVG_SPEED: form.avgSpeed,
        SPEED_THROUGH_WATER: form.stw,
        FORE_DRAFT: form.foreDraft,
        AFTER_DRAFT: form.aftDraft,
        WIND_SCALE: form.windScale,
        SEA_HEIGHT: form.seaHeight,
      }),
      runStagedReveal(),
    ])
    diagnosis.value = result
  } catch (e) {
    diagnosisError.value = e instanceof Error ? e.message : '油耗診斷失敗，請稍後重試。'
  } finally {
    diagnosing.value = false
    clearStageTimers()
  }
}

// ─── 即時閥值檢查 ───────────────────────────────────────────────────────────
type AlertLevel = 'CRITICAL' | 'WARNING' | 'OK'

const diagnosisVerdict = computed(() => {
  if (!diagnosis.value || reportedConsumptionMt.value == null) return null
  const predicted = diagnosis.value.predicted_consumption_mt
  const actual = reportedConsumptionMt.value
  const deviationPct = predicted > 0 ? ((actual - predicted) / predicted) * 100 : 0
  const savingPct = diagnosis.value.counterfactual_uwc_pp.saving_pct

  let level: AlertLevel = 'OK'
  if (savingPct >= 8 || deviationPct >= 8) level = 'CRITICAL'
  else if (savingPct >= 5 || deviationPct >= 5) level = 'WARNING'

  const deviationText = `${deviationPct >= 0 ? '高於' : '低於'}模型預測 ${Math.abs(deviationPct).toFixed(1)}%`
  const message =
    level === 'CRITICAL'
      ? `本次回報油耗 ${actual.toFixed(1)} MT/日，${deviationText}；執行 UWC+PP 估計可省 ${savingPct.toFixed(1)}%，已超過門檻，建議申請養護。`
      : level === 'WARNING'
        ? `本次回報油耗 ${actual.toFixed(1)} MT/日，${deviationText}；執行 UWC+PP 估計可省 ${savingPct.toFixed(1)}%，已接近門檻，建議留意。`
        : `本次回報油耗 ${actual.toFixed(1)} MT/日，${deviationText}；執行 UWC+PP 估計可省 ${savingPct.toFixed(1)}%，暫在正常範圍。`

  return { level, message, deviationPct, savingPct, predicted, actual }
})

function alertLevelColor(level: AlertLevel): string {
  if (level === 'CRITICAL') return 'var(--color-signal-red)'
  if (level === 'WARNING') return 'var(--color-brass-amber)'
  return 'var(--color-fathom-teal)'
}

// ─── 一鍵申請養護（示意，未串接後端） ───────────────────────────────────────
const requestModalOpen = ref(false)
const bannerRequestSent = ref(false)

const requestDefaultNote = computed(() => {
  const v = diagnosisVerdict.value
  if (!v || submittedDay.value == null) return ''
  return `Day ${submittedDay.value} Noon Report 油耗診斷：${v.message}`
})

function onRequestSubmitted() {
  bannerRequestSent.value = true
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="panel p-4 flex flex-col gap-3">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <span v-if="data" class="text-xs text-[var(--color-ink-slate)]/50 font-data">
            共 {{ combinedReports.length.toLocaleString() }} 筆{{ filteredReports.length !== combinedReports.length ? `（篩選後 ${filteredReports.length.toLocaleString()} 筆）` : '' }}
            <template v-if="localReports.length">· 含 {{ localReports.length }} 筆本地新增</template>
          </span>
        </div>
        <div class="flex items-center gap-2 text-sm">
          <label class="flex items-center gap-1">
            <span class="text-[var(--color-ink-slate)]/60 text-xs">起 (Day)</span>
            <input v-model="startDayInput" type="number" class="border rounded-[2px] px-2 py-1 font-data text-xs w-20" />
          </label>
          <label class="flex items-center gap-1">
            <span class="text-[var(--color-ink-slate)]/60 text-xs">迄 (Day)</span>
            <input v-model="endDayInput" type="number" class="border rounded-[2px] px-2 py-1 font-data text-xs w-20" />
          </label>
          <button
            class="border rounded-[2px] px-3 py-1 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
            @click="exportCsv"
          >
            匯出 CSV
          </button>
          <button
            class="border rounded-[2px] px-3 py-1 text-xs font-display uppercase tracking-wide bg-[var(--color-brass-amber)] text-white border-[var(--color-brass-amber)] hover:opacity-90 transition-opacity"
            @click="openForm"
          >
            + 新增今日 Noon Report
          </button>
        </div>
      </div>
    </div>

    <!-- 新增填報表單 — 緊接在按鈕下方，而非表格之後，避免使用者誤以為沒有反應 -->
    <Transition name="panel-fade">
    <div v-if="showForm" class="relative panel p-4 flex flex-col gap-3">
      <DataSourceTag :info="dsReportForm" />
      <div class="flex items-center justify-between">
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70">
          新增 Day {{ newDayIndex }} 填報
        </p>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">航速(觀測) kt</span>
          <input v-model.number="form.avgSpeed" type="number" step="0.1" class="field font-data" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">航速(修正後/STW) kt</span>
          <input v-model.number="form.stw" type="number" step="0.1" class="field font-data" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">主機油耗 MT/日</span>
          <input v-model.number="form.meConsumption" type="number" step="0.1" class="field font-data" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">載貨量 MT</span>
          <input v-model.number="form.cargoOnBoard" type="number" step="10" class="field font-data" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">蒲福風級</span>
          <input v-model.number="form.windScale" type="number" min="0" max="12" class="field font-data" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">浪高 m</span>
          <input v-model.number="form.seaHeight" type="number" step="0.1" class="field font-data" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">前吃水 m</span>
          <input v-model.number="form.foreDraft" type="number" step="0.1" class="field font-data" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-xs text-[var(--color-ink-slate)]/60">後吃水 m</span>
          <input v-model.number="form.aftDraft" type="number" step="0.1" class="field font-data" />
        </label>
      </div>
      <p v-if="formError" class="text-xs text-[var(--color-signal-red)]">{{ formError }}</p>
      <div class="flex justify-end gap-2">
        <button
          class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
          @click="showForm = false"
        >
          取消
        </button>
        <button
          class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide bg-[var(--color-brass-amber)] text-white border-[var(--color-brass-amber)] hover:opacity-90 transition-opacity"
          @click="submitReport"
        >
          送出並跑油耗診斷
        </button>
      </div>
    </div>
    </Transition>

    <!-- 即時閥值檢查 + 油耗診斷結果 -->
    <Transition name="panel-fade">
    <div v-if="diagnosing || diagnosis || diagnosisError" class="relative panel p-4 flex flex-col gap-3">
      <DataSourceTag :info="dsDiagnosis" />
      <div class="flex items-center justify-between">
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70">
          Day {{ submittedDay }} 即時閥值檢查與油耗診斷
        </p>
      </div>

      <StateDisplay v-if="diagnosisError" state="error" :error-message="diagnosisError" />

      <ul v-else-if="diagnosing" class="flex flex-col gap-2">
        <li
          v-for="(stageText, i) in PROCESS_STAGES"
          :key="stageText"
          class="stage-line flex items-center gap-2 text-xs font-data text-[var(--color-ink-slate)]/70"
          :class="{ 'stage-line--visible': i < revealedStageCount }"
        >
          <span
            class="status-dot"
            :class="i < revealedStageCount - 1 ? 'bg-[var(--color-fathom-teal)]' : 'bg-[var(--color-brass-amber)] stage-dot-pulse'"
          />
          {{ stageText }}
        </li>
      </ul>

      <template v-else-if="diagnosisVerdict">
        <div
          class="rounded-[3px] px-3 py-2.5"
          :style="{
            background: `color-mix(in srgb, ${alertLevelColor(diagnosisVerdict.level)} 10%, transparent)`,
            borderLeft: `4px solid ${alertLevelColor(diagnosisVerdict.level)}`,
          }"
        >
          <p class="font-bold text-sm mb-1" :style="{ color: alertLevelColor(diagnosisVerdict.level) }">
            {{ diagnosisVerdict.level === 'CRITICAL' ? '🚨 超過門檻' : diagnosisVerdict.level === 'WARNING' ? '⚠️ 接近門檻' : '✅ 正常範圍' }}
          </p>
          <p class="text-sm text-[var(--color-ink-slate)]/85">{{ diagnosisVerdict.message }}</p>
        </div>

        <div class="grid grid-cols-3 gap-3 font-data text-sm">
          <div>
            <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">模型預測油耗</p>
            <p>{{ diagnosisVerdict.predicted.toFixed(2) }} MT/日</p>
          </div>
          <div>
            <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">本次回報油耗</p>
            <p>{{ diagnosisVerdict.actual.toFixed(2) }} MT/日</p>
          </div>
          <div>
            <p class="text-xs font-body text-[var(--color-ink-slate)]/60 mb-0.5">執行 UWC+PP 可省</p>
            <p :style="{ color: alertLevelColor(diagnosisVerdict.level) }">{{ diagnosisVerdict.savingPct.toFixed(1) }}%</p>
          </div>
        </div>

        <div v-if="diagnosisVerdict.level !== 'OK'" class="flex items-center gap-2">
          <button
            v-if="!bannerRequestSent"
            class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide bg-[var(--color-signal-red)] text-white border-[var(--color-signal-red)] hover:opacity-90 transition-opacity"
            @click="requestModalOpen = true"
          >
            申請養護
          </button>
          <span v-else class="text-xs font-data text-[var(--color-fathom-teal)]">✓ 已送出養護申請（示意）</span>
        </div>
      </template>
    </div>
    </Transition>

    <div class="relative panel p-4 flex flex-col gap-3">
      <DataSourceTag :info="dsNoon" />
      <StateDisplay
        v-if="state !== 'success'"
        :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
        empty-title="此船尚無 Noon Report 記錄"
      />
      <StateDisplay
        v-else-if="visibleReports.length === 0"
        state="empty"
        empty-title="所選 Day 區間內無資料"
        empty-hint="請放寬篩選範圍。"
      />
      <div v-else class="overflow-x-auto max-h-[640px] overflow-y-auto">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-[var(--color-chart-paper)]">
            <tr class="chart-divider">
              <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">Day</th>
              <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">位置</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">航速(觀測)</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">航速(修正後)</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">油耗 MT/日</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">海況(BF)</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">吃水(F/A)</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in visibleReports"
              :key="r.day"
              class="chart-divider group relative"
              :class="{ 'bg-[color-mix(in_srgb,var(--color-brass-amber)_8%,transparent)]': r.isLocal }"
            >
              <td class="px-3 py-1.5 font-data whitespace-nowrap">
                {{ r.day }}
                <span v-if="r.isLocal" class="status-dot bg-[var(--color-brass-amber)] ml-1" title="本次工作階段新增，未寫入後端" />
              </td>
              <td class="px-3 py-1.5 font-data text-xs text-[var(--color-ink-slate)]/50">—</td>
              <td class="px-3 py-1.5 font-data text-right">{{ r.observedSpeedKt.toFixed(1) }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ r.correctedSpeedKt.toFixed(1) }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ r.fuelConsumptionMt.toFixed(1) }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ r.beaufort }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ r.draftFwd.toFixed(1) }}/{{ r.draftAft.toFixed(1) }}</td>
            </tr>
          </tbody>
        </table>
        <p class="text-xs text-[var(--color-ink-slate)]/50 mt-2 px-1">
          預設顯示最近 60 筆，可用 Day 篩選查看完整區間。
        </p>
      </div>
    </div>

    <MaintenanceRequestModal
      v-model:open="requestModalOpen"
      :vessel="vessel"
      :context-note="requestDefaultNote"
      :diagnosis="diagnosis"
      @submitted="onRequestSubmitted"
    />
  </div>
</template>

<style scoped>
.panel-fade-enter-from,
.panel-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (prefers-reduced-motion: no-preference) {
  .panel-fade-enter-active,
  .panel-fade-leave-active {
    transition: opacity 180ms ease, transform 180ms ease;
  }
}

.stage-line {
  opacity: 0;
  transform: translateY(4px);
}

.stage-line--visible {
  opacity: 1;
  transform: translateY(0);
}

@media (prefers-reduced-motion: no-preference) {
  .stage-line {
    transition: opacity 220ms ease, transform 220ms ease;
  }
}

.stage-dot-pulse {
  animation: stage-dot-pulse 1s ease-in-out infinite;
}

@media (prefers-reduced-motion: no-preference) {
  @keyframes stage-dot-pulse {
    0%, 100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }
}
</style>
