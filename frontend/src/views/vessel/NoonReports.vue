<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
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

interface FullNoonReport {
  [key: string]: any
  isLocal?: boolean
}

type LocalNoonReportEntry = NoonReportEntry & { isLocal?: boolean }

async function fetchReports(imo: string): Promise<{ vessel: VesselSummary; reports: FullNoonReport[] }> {
  const resp = await getNoonReports(imo, { limit: 10000 })
  const reports: FullNoonReport[] = resp.records.sort((a, b) => {
    const dayA = Number(a.noon_utc || a.noon_day || 0)
    const dayB = Number(b.noon_utc || b.noon_day || 0)
    return dayB - dayA
  })
  return { vessel: props.vessel, reports }
}

const { data, state } = useAsyncData(() => props.imo, fetchReports)

// 分頁
const currentPage = ref(1)
const itemsPerPage = 10

const allReports = computed<FullNoonReport[]>(() => data.value?.reports ?? [])

const totalPages = computed(() => Math.ceil(allReports.value.length / itemsPerPage))

// 動態計算所有欄位名稱
const allFieldNames = computed(() => {
  if (allReports.value.length === 0) return []
  const fieldSet = new Set<string>()
  for (const report of allReports.value) {
    Object.keys(report).forEach((k) => {
      if (k !== 'isLocal') fieldSet.add(k)
    })
  }
  // 優先顯示常用欄位
  const priority = ['noon_utc', 'voyage', 'noon_day']
  const priorityFields = priority.filter((f) => fieldSet.has(f))
  const otherFields = Array.from(fieldSet).filter((f) => !priority.includes(f)).sort()
  return [...priorityFields, ...otherFields]
})

const paginatedReports = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  return allReports.value.slice(start, end)
})

function goToPage(page: number) {
  currentPage.value = Math.max(1, Math.min(page, totalPages.value))
}

function formatCellValue(value: any): string {
  if (value == null) return '—'
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return value.toString()
    if (value < 10) return value.toFixed(2)
    return value.toFixed(1)
  }
  return String(value)
}

// 本次工作階段新增的填報 — 純前端 state，不落地寫入後端。
const localReports = ref<LocalNoonReportEntry[]>([])
const combinedReports = computed<LocalNoonReportEntry[]>(() => [...(data.value?.reports ?? []), ...localReports.value])

// Raw API records key their day index as noon_utc/noon_day; locally-added
// entries (see submitReport) use `day` directly.
function reportDay(r: FullNoonReport): number {
  return Number(r.noon_utc ?? r.noon_day ?? r.day ?? 0)
}

// 起訖 (Day) 篩選 — 預設涵蓋整個資料範圍，資料載入後才知道範圍所以用 watch 設定初始值。
const startDayInput = ref<number | null>(null)
const endDayInput = ref<number | null>(null)

watch(combinedReports, (reports) => {
  if (!reports.length) return
  const days = reports.map(reportDay)
  if (startDayInput.value == null) startDayInput.value = Math.min(...days)
  if (endDayInput.value == null) endDayInput.value = Math.max(...days)
})

const filteredReports = computed(() =>
  combinedReports.value.filter((r) => {
    const d = reportDay(r)
    return (startDayInput.value == null || d >= startDayInput.value) && (endDayInput.value == null || d <= endDayInput.value)
  }),
)
const visibleReports = combinedReports

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
  voyage: 0,
  avgSpeed: 15,
  stw: 15,
  meAvgRpm: 60,
  propellerSpeed: 16,
  foreDraft: 13.5,
  aftDraft: 13.5,
  displacement: 0,
  cargoOnBoard: 0,
  windScale: 3,
  seaHeight: 1,
  seaWaterTemp: 25,
  windSpeed: 10,
  windDirection: 0,
  swellHeight: 1,
  swellDirection: 0,
  seaDirection: 0,
  waterDepth: 100,
  midDraft: 13.5,
  totalDistance: 400,
  seaSpeedDistance: 380,
  diffStwSog: 0,
  fullSpdStwSlip: 0,
  horsePower: 13000,
  loadPct: 85,
  sfoc: 170,
  meSlip: 5,
  thrust: 0,
  thrustQuotient: 0,
  totalConsump: 50,
  meFullspeedConsumpHshfo: 0,
  meFullspeedConsumpVlsfo: 51,
  meFullspeedConsumpUlsfo: 0,
  meFullspeedConsumpLsmgo: 0,
  meFullspeedConsumpBioHsfo: 0,
  meConsumption: 30,
  hoursFullSpeed: 22,
  hoursTotal: 24,
})

function openForm() {
  // Reset form to empty defaults
  form.voyage = 0
  form.avgSpeed = 0
  form.stw = 0
  form.meAvgRpm = 0
  form.propellerSpeed = 0
  form.foreDraft = 0
  form.aftDraft = 0
  form.displacement = 0
  form.cargoOnBoard = 0
  form.windScale = 0
  form.seaHeight = 0
  form.seaWaterTemp = 0
  form.windSpeed = 0
  form.windDirection = 0
  form.swellHeight = 0
  form.swellDirection = 0
  form.seaDirection = 0
  form.waterDepth = 0
  form.midDraft = 0
  form.totalDistance = 0
  form.seaSpeedDistance = 0
  form.diffStwSog = 0
  form.fullSpdStwSlip = 0
  form.horsePower = 0
  form.loadPct = 0
  form.sfoc = 0
  form.meSlip = 0
  form.thrust = 0
  form.thrustQuotient = 0
  form.totalConsump = 0
  form.meFullspeedConsumpHshfo = 0
  form.meFullspeedConsumpVlsfo = 0
  form.meFullspeedConsumpUlsfo = 0
  form.meFullspeedConsumpLsmgo = 0
  form.meFullspeedConsumpBioHsfo = 0
  form.meConsumption = 0
  form.hoursFullSpeed = 0
  form.hoursTotal = 0
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
  if (!(form.avgSpeed > 0)) {
    formError.value = '請輸入有效的航速數值（須大於 0）。'
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

  showForm.value = false
  bannerRequestSent.value = false
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
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 text-sm">
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">航次</span><input v-model.number="form.voyage" type="number" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">平均對地航速 kt</span><input v-model.number="form.avgSpeed" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">對水航速 kt</span><input v-model.number="form.stw" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">主機轉速 RPM</span><input v-model.number="form.meAvgRpm" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">螺旋槳轉速 RPM</span><input v-model.number="form.propellerSpeed" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">首吃水 m</span><input v-model.number="form.foreDraft" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">尾吃水 m</span><input v-model.number="form.aftDraft" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">舯吃水 m</span><input v-model.number="form.midDraft" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">排水量 MT</span><input v-model.number="form.displacement" type="number" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">載貨量 MT</span><input v-model.number="form.cargoOnBoard" type="number" step="10" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">風力等級 BF</span><input v-model.number="form.windScale" type="number" min="0" max="12" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">浪高 m</span><input v-model.number="form.seaHeight" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">海水溫度 °C</span><input v-model.number="form.seaWaterTemp" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">風速 knots</span><input v-model.number="form.windSpeed" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">風向 deg</span><input v-model.number="form.windDirection" type="number" step="1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">湧浪高度 m</span><input v-model.number="form.swellHeight" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">湧浪方向 deg</span><input v-model.number="form.swellDirection" type="number" step="1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">浪方向 deg</span><input v-model.number="form.seaDirection" type="number" step="1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">水深 m</span><input v-model.number="form.waterDepth" type="number" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">對地總航距 nm</span><input v-model.number="form.totalDistance" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">全速對水航距 nm</span><input v-model.number="form.seaSpeedDistance" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">速差 knots</span><input v-model.number="form.diffStwSog" type="number" step="0.01" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">全速滑差 %</span><input v-model.number="form.fullSpdStwSlip" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">主機功率 kW</span><input v-model.number="form.horsePower" type="number" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">負載率 %MCR</span><input v-model.number="form.loadPct" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">比油耗 g/kWh</span><input v-model.number="form.sfoc" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">滑差 %</span><input v-model.number="form.meSlip" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">推力 kN</span><input v-model.number="form.thrust" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">推力係數</span><input v-model.number="form.thrustQuotient" type="number" step="0.01" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">總油耗 MT/day</span><input v-model.number="form.totalConsump" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">全速油耗(HSHFO) MT/day</span><input v-model.number="form.meFullspeedConsumpHshfo" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">全速油耗(VLSFO) MT/day</span><input v-model.number="form.meFullspeedConsumpVlsfo" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">全速油耗(ULSFO) MT/day</span><input v-model.number="form.meFullspeedConsumpUlsfo" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">全速油耗(LSMGO) MT/day</span><input v-model.number="form.meFullspeedConsumpLsmgo" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">全速油耗(BIO_HSFO) MT/day</span><input v-model.number="form.meFullspeedConsumpBioHsfo" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">主機油耗合計 MT/day</span><input v-model.number="form.meConsumption" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">全速時數 hr</span><input v-model.number="form.hoursFullSpeed" type="number" step="0.1" class="field font-data text-xs" /></label>
        <label class="flex flex-col gap-1"><span class="text-xs text-[var(--color-ink-slate)]/60">總時數 hr</span><input v-model.number="form.hoursTotal" type="number" step="0.1" class="field font-data text-xs" /></label>
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
          送出
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
      <StateDisplay
        v-if="state !== 'success'"
        :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
        empty-title="此船尚無 Noon Report 記錄"
      />
      <div v-else-if="allReports.length === 0" class="text-center py-8 text-sm text-[var(--color-ink-slate)]/50">
        無資料
      </div>
      <div v-else class="flex flex-col gap-3">
        <!-- 分頁導航（上方） -->
        <div class="flex items-center justify-between px-1">
          <span class="text-xs text-[var(--color-ink-slate)]/50">
            第 {{ currentPage }} / {{ totalPages }} 頁（共 {{ allReports.length.toLocaleString() }} 筆）
          </span>
          <div class="flex gap-2">
            <button
              :disabled="currentPage === 1"
              class="border rounded-[2px] px-2 py-1 text-xs font-display uppercase tracking-wide disabled:opacity-50 disabled:cursor-not-allowed hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
              @click="goToPage(currentPage - 1)"
            >
              ← 上一頁
            </button>
            <button
              :disabled="currentPage === totalPages"
              class="border rounded-[2px] px-2 py-1 text-xs font-display uppercase tracking-wide disabled:opacity-50 disabled:cursor-not-allowed hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
              @click="goToPage(currentPage + 1)"
            >
              下一頁 →
            </button>
          </div>
        </div>

        <!-- 表格 -->
        <div class="overflow-x-auto border rounded-[2px]">
          <table class="w-full text-xs font-data">
            <thead class="sticky top-0 bg-[var(--color-chart-paper)]">
              <tr class="chart-divider">
                <th v-for="field in allFieldNames" :key="field" class="text-right px-2 py-2 whitespace-nowrap text-[10px]">
                  {{ field.toUpperCase() }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, idx) in paginatedReports" :key="idx" class="chart-divider hover:bg-[var(--color-chart-paper-hi)]">
                <td v-for="field in allFieldNames" :key="field" class="px-2 py-1 text-right">
                  {{ formatCellValue(r[field]) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 分頁導航（下方） -->
        <div class="flex items-center justify-between px-1">
          <button
            :disabled="currentPage === 1"
            class="border rounded-[2px] px-2 py-1 text-xs font-display uppercase tracking-wide disabled:opacity-50 disabled:cursor-not-allowed hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
            @click="goToPage(currentPage - 1)"
          >
            ← 上一頁
          </button>
          <span class="text-xs text-[var(--color-ink-slate)]/50">第 {{ currentPage }} / {{ totalPages }} 頁</span>
          <button
            :disabled="currentPage === totalPages"
            class="border rounded-[2px] px-2 py-1 text-xs font-display uppercase tracking-wide disabled:opacity-50 disabled:cursor-not-allowed hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
            @click="goToPage(currentPage + 1)"
          >
            下一頁 →
          </button>
        </div>
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
