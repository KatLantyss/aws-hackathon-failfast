<script setup lang="ts">
// 提交養護工單申請 — 示意呈現用元件，尚未串接後端 API。開啟時彙整同船「維護
// 紀錄／速度損失／速損歸因／油耗預測／維修效能分析」五頁已在用的真實/混合資
// 料，組成區塊卡片 + 可編輯文字摘要，讓使用者送出前先做 final check。送出後
// 只更新前端呼叫端狀態（見 v-model:open + submitted 事件），重新整理頁面即重置。
import { computed, ref, watch } from 'vue'
import type { VesselSummary, MaintenanceCorrelationResponse } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import type { BackendFuelPredictionResult, BackendSpeedLossAttribution } from '@/services/backend'
import { getSpeedLossAttribution, predictFuelConsumption } from '@/services/backend'
import { fetchCorrelation } from '@/composables/useDataSource'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { formatUsd, formatDay, speedLossColor, URGENCY_LABEL, URGENCY_COLOR } from '@/utils/format'

const props = defineProps<{
  vessel: VesselSummary
  /** 呼叫端想附加在摘要最前面的情境備註，例如 NoonReports 的診斷結論 */
  contextNote?: string
  /** 若呼叫端已經有現成的油耗診斷結果（NoonReports NR-03），直接重用，不重打 API */
  diagnosis?: BackendFuelPredictionResult | null
}>()
const emit = defineEmits<{ submitted: [note: string] }>()
const open = defineModel<boolean>('open', { default: false })

const note = ref('')
const noteAutoFilled = ref(true)
const submitting = ref(false)
const justSubmitted = ref(false)

const summaryLoading = ref(false)
const correlation = ref<MaintenanceCorrelationResponse | null>(null)
const attribution = ref<BackendSpeedLossAttribution | null>(null)
const fuelResult = ref<BackendFuelPredictionResult | null>(null)
let loadedForImo: string | null = null

const CATEGORY_LABELS: Record<string, string> = {
  'hull+propeller': '船殼+螺旋槳',
  hull: '船殼',
  propeller: '螺旋槳',
  inspection_only: '純檢查（無預期改善）',
  other: '其他',
}

const topAttribution = computed(() => {
  if (!attribution.value) return null
  const entries = Object.entries(attribution.value.summary) as [string, number][]
  if (!entries.length) return null
  const [category, avgDelta] = entries.sort((a, b) => b[1] - a[1])[0]
  return { label: CATEGORY_LABELS[category] ?? category, avgDelta }
})

const effectiveFuelResult = computed(() => props.diagnosis ?? fuelResult.value)

function buildSummaryText(): string {
  const v = props.vessel
  const lines: string[] = []
  if (props.contextNote) lines.push(props.contextNote)

  lines.push(
    `【維護紀錄】最後養護：${v.lastEventType ?? '無記錄'}；累計 ${v.totalMaintEvents ?? 0} 次事件；距上次船殼清洗 ${v.daysSinceHullClean} 天。`,
  )

  if (v.avgSpeedLossPct != null) {
    const trendText = v.speedLossTrend == null ? '' : `（趨勢：${v.speedLossTrend > 0 ? '惡化' : '改善'} ${Math.abs(v.speedLossTrend).toFixed(2)}%）`
    lines.push(`【速度損失】近90天平均 ${v.avgSpeedLossPct.toFixed(2)}%，最新 ${v.speedLossPct.toFixed(2)}%${trendText}。`)
  }

  if (topAttribution.value) {
    lines.push(`【速損歸因】主要歸因：${topAttribution.value.label}（平均改善 ${topAttribution.value.avgDelta.toFixed(2)}%）。`)
  }

  if (effectiveFuelResult.value) {
    const f = effectiveFuelResult.value
    lines.push(
      `【油耗預測】模型預測油耗 ${f.predicted_consumption_mt.toFixed(2)} MT/日；執行 UWC+PP 預估可省 ${f.counterfactual_uwc_pp.saving_pct.toFixed(1)}%（年化約 ${formatUsd(f.counterfactual_uwc_pp.est_annual_saving_usd)}）。`,
    )
  }

  if (correlation.value) {
    const t = correlation.value.optimalTiming
    lines.push(
      `【維修效能分析】建議動作：${t.recommendedAction}，急迫程度：${URGENCY_LABEL[t.urgency]}，建議窗口 ${formatDay(t.windowStartDay)}–${formatDay(t.windowEndDay)}。${t.reasoning}`,
    )
  }

  return lines.join('\n')
}

async function loadSummaryData() {
  const imo = props.vessel.imo
  if (loadedForImo !== imo) {
    loadedForImo = imo
    summaryLoading.value = true
    correlation.value = null
    attribution.value = null
    fuelResult.value = null

    const tasks: Promise<void>[] = [
      fetchCorrelation(imo).then((r) => {
        correlation.value = r
      }).catch(() => {}),
      getSpeedLossAttribution(imo).then((r) => {
        attribution.value = r
      }).catch(() => {}),
    ]

    if (!props.diagnosis) {
      const v = props.vessel
      tasks.push(
        predictFuelConsumption({
          vessel_id: imo,
          noon_day: v.dataDayMax ?? undefined,
          AVG_SPEED: v.avgSpeedKn ?? 15,
          SPEED_THROUGH_WATER: v.avgStwKn ?? v.avgSpeedKn ?? 15,
          FORE_DRAFT: v.avgForeDraftM ?? 13.5,
          AFTER_DRAFT: v.avgAftDraftM ?? 13.5,
          WIND_SCALE: v.avgWindScale ?? 3,
          SEA_HEIGHT: v.avgSeaHeightM ?? 1,
        }).then((r) => {
          fuelResult.value = r
        }).catch(() => {}),
      )
    }

    await Promise.allSettled(tasks)
    summaryLoading.value = false
  }

  if (noteAutoFilled.value) note.value = buildSummaryText()
}

watch(open, (isOpen) => {
  if (isOpen) {
    submitting.value = false
    justSubmitted.value = false
    note.value = props.contextNote ?? ''
    noteAutoFilled.value = true
    loadSummaryData()
  }
})

function onNoteInput() {
  noteAutoFilled.value = false
}

const dsInfo: DataSourceInfo = {
  status: 'hybrid',
  endpoint: [
    'GET /api/v1/vessels/{vessel_id}/maintenance-events',
    'GET /api/v1/vessels/{vessel_id}/speed-loss-attribution',
    'GET /api/v1/vessels/{vessel_id}/maintenance-recommendation',
    'POST /api/v1/predict/fuel-consumption',
  ],
  description:
    '五張卡片彙整同船其他頁籤已在用的真實/混合資料；下方文字摘要是前端模板字串代入這些欄位組成（同「維修效能分析」頁 COR-08「AI 分析摘要」的手法）。送出本身仍是純前端 stub，未呼叫任何寫入 API，重新整理頁面即會重置。',
  fields: [
    { ui: '維護紀錄卡', source: 'vessel.lastEventType / totalMaintEvents / daysSinceHullClean（real，來自 maintenance-events / fleet/summary）' },
    { ui: '速度損失卡', source: 'vessel.avgSpeedLossPct / speedLossPct / speedLossTrend（real）' },
    { ui: '速損歸因卡', source: 'speed-loss-attribution 回傳 summary，取平均改善最高的分類（real）' },
    { ui: '油耗預測卡', source: 'predict-fuel-consumption 回傳（real；若由 Noon Report 帶入既有診斷結果則不重打）' },
    { ui: '維修效能分析卡', source: 'maintenance-recommendation 等混合計算的 optimalTiming（hybrid，同維修效能分析頁 COR-03）' },
  ],
}

function close() {
  open.value = false
}

async function submit() {
  submitting.value = true
  await new Promise((resolve) => setTimeout(resolve, 500))
  submitting.value = false
  justSubmitted.value = true
  emit('submitted', note.value)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/50" @click="close" />
      <div
        class="relative panel p-5 w-full max-w-3xl max-h-[85vh] overflow-y-auto flex flex-col gap-4"
        role="dialog"
        aria-modal="true"
        aria-label="申請養護"
      >
        <DataSourceTag :info="dsInfo" />
        <div class="flex items-center justify-between pr-8">
          <p class="font-display text-sm tracking-wide">申請養護 Final Check — {{ vessel.name }}</p>
          <button type="button" class="text-[var(--color-ink-slate)]/50 hover:text-[var(--color-ink-slate)] text-lg leading-none" @click="close">
            ✕
          </button>
        </div>

        <template v-if="!justSubmitted">
          <p class="text-xs text-[var(--color-ink-slate)]/60">
            送出申請前，先確認以下五項重點資訊；下方文字摘要已自動彙整，可直接編輯後送出。
          </p>

          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            <!-- 維護紀錄 -->
            <div class="panel p-3 border-l-4" style="border-left-color: var(--color-ink-slate)">
              <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-1.5">維護紀錄</p>
              <p class="font-data text-sm">{{ vessel.lastEventType ?? '無記錄' }}</p>
              <p class="text-xs text-[var(--color-ink-slate)]/60 mt-1">累計 {{ vessel.totalMaintEvents ?? 0 }} 次事件</p>
              <p class="text-xs text-[var(--color-ink-slate)]/60">距上次船殼清洗 {{ vessel.daysSinceHullClean }} 天</p>
            </div>

            <!-- 速度損失 -->
            <div class="panel p-3 border-l-4" :style="{ borderLeftColor: speedLossColor(vessel.speedLossPct) }">
              <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-1.5">速度損失</p>
              <p class="font-data text-sm" :style="{ color: speedLossColor(vessel.speedLossPct) }">最新 {{ vessel.speedLossPct.toFixed(2) }}%</p>
              <p v-if="vessel.avgSpeedLossPct != null" class="text-xs text-[var(--color-ink-slate)]/60 mt-1">近90天平均 {{ vessel.avgSpeedLossPct.toFixed(2) }}%</p>
              <p v-if="vessel.speedLossTrend != null" class="text-xs text-[var(--color-ink-slate)]/60">
                趨勢：{{ vessel.speedLossTrend > 0 ? '↑ 惡化' : '↓ 改善' }} {{ Math.abs(vessel.speedLossTrend).toFixed(2) }}%
              </p>
            </div>

            <!-- 速損歸因 -->
            <div class="panel p-3 border-l-4" style="border-left-color: var(--color-brass-amber)">
              <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-1.5">速損歸因</p>
              <p v-if="summaryLoading" class="text-xs text-[var(--color-ink-slate)]/40 animate-pulse">載入中…</p>
              <template v-else-if="topAttribution">
                <p class="font-data text-sm">{{ topAttribution.label }}</p>
                <p class="text-xs text-[var(--color-ink-slate)]/60 mt-1">平均改善 {{ topAttribution.avgDelta.toFixed(2) }}%</p>
              </template>
              <p v-else class="text-xs text-[var(--color-ink-slate)]/40">資料暫缺</p>
            </div>

            <!-- 油耗預測 -->
            <div class="panel p-3 border-l-4" style="border-left-color: var(--color-fathom-teal)">
              <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-1.5">油耗預測</p>
              <p v-if="!effectiveFuelResult && summaryLoading" class="text-xs text-[var(--color-ink-slate)]/40 animate-pulse">載入中…</p>
              <template v-else-if="effectiveFuelResult">
                <p class="font-data text-sm">預測 {{ effectiveFuelResult.predicted_consumption_mt.toFixed(2) }} MT/日</p>
                <p class="text-xs text-[var(--color-fathom-teal)] mt-1">UWC+PP 可省 {{ effectiveFuelResult.counterfactual_uwc_pp.saving_pct.toFixed(1) }}%</p>
                <p class="text-xs text-[var(--color-ink-slate)]/60">年化約 {{ formatUsd(effectiveFuelResult.counterfactual_uwc_pp.est_annual_saving_usd) }}</p>
              </template>
              <p v-else class="text-xs text-[var(--color-ink-slate)]/40">資料暫缺</p>
            </div>

            <!-- 維修效能分析（現況） -->
            <div class="panel p-3 border-l-4" style="border-left-color: var(--color-ink-slate)">
              <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-1.5">維修效能分析</p>
              <p v-if="summaryLoading" class="text-xs text-[var(--color-ink-slate)]/40 animate-pulse">載入中…</p>
              <template v-else-if="correlation">
                <p class="font-data text-sm">
                  Speed Loss {{ correlation.optimalTiming.currentSpeedLossPct.toFixed(1) }}%
                  <span class="text-xs text-[var(--color-ink-slate)]/50">（閾值 {{ correlation.optimalTiming.optimalThresholdPct.toFixed(1) }}%）</span>
                </p>
                <p v-if="correlation.typeEffectiveness.length" class="text-xs text-[var(--color-ink-slate)]/60 mt-1">
                  歷史最有效：{{ correlation.typeEffectiveness[0].type }}（改善 {{ correlation.typeEffectiveness[0].avgImprovementPct.toFixed(1) }}%）
                </p>
                <p class="text-xs text-[var(--color-ink-slate)]/60">
                  累計 {{ correlation.summary.totalEvents }} 次事件，平均改善 {{ correlation.summary.avgImprovementPct.toFixed(1) }}%
                </p>
              </template>
              <p v-else class="text-xs text-[var(--color-ink-slate)]/40">資料暫缺</p>
            </div>

            <!-- 建議動作 -->
            <div
              class="panel p-3 border-l-4"
              :style="{
                borderLeftColor: correlation ? URGENCY_COLOR[correlation.optimalTiming.urgency] : 'var(--color-ink-slate)',
                background: correlation ? `color-mix(in srgb, ${URGENCY_COLOR[correlation.optimalTiming.urgency]} 8%, transparent)` : undefined,
              }"
            >
              <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-1.5">建議動作</p>
              <p v-if="summaryLoading" class="text-xs text-[var(--color-ink-slate)]/40 animate-pulse">載入中…</p>
              <template v-else-if="correlation">
                <p class="font-data text-sm font-semibold" :style="{ color: URGENCY_COLOR[correlation.optimalTiming.urgency] }">
                  {{ correlation.optimalTiming.recommendedAction }}
                  <span class="text-xs font-normal">（急迫程度：{{ URGENCY_LABEL[correlation.optimalTiming.urgency] }}）</span>
                </p>
                <p class="text-xs text-[var(--color-ink-slate)]/60 mt-1">
                  建議窗口 {{ formatDay(correlation.optimalTiming.windowStartDay) }}–{{ formatDay(correlation.optimalTiming.windowEndDay) }}
                </p>
              </template>
              <p v-else class="text-xs text-[var(--color-ink-slate)]/40">資料暫缺</p>
            </div>
          </div>

          <label class="flex flex-col gap-1 text-sm">
            <span class="text-xs text-[var(--color-ink-slate)]/60">彙整摘要（可編輯，將作為申請備註送出）</span>
            <textarea
              v-model="note"
              rows="7"
              class="field font-body text-sm"
              placeholder="正在自動彙整重點資訊…"
              @input="onNoteInput"
            />
          </label>

          <div class="flex justify-end gap-2">
            <button
              type="button"
              class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
              @click="close"
            >
              取消
            </button>
            <button
              type="button"
              class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide bg-[var(--color-brass-amber)] text-white border-[var(--color-brass-amber)] hover:opacity-90 transition-opacity disabled:opacity-40"
              :disabled="submitting"
              @click="submit"
            >
              {{ submitting ? '送出中…' : '確認送出申請' }}
            </button>
          </div>
        </template>

        <template v-else>
          <div class="flex flex-col items-center gap-2 py-4 text-center">
            <span class="status-dot bg-[var(--color-fathom-teal)]" />
            <p class="font-display text-sm">已送出養護申請</p>
            <p class="text-xs text-[var(--color-ink-slate)]/60 max-w-xs">
              狀態已更新為「已申請養護」（僅前端示意，尚未串接後端 API）。
            </p>
          </div>
          <div class="flex justify-end">
            <button
              type="button"
              class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
              @click="close"
            >
              關閉
            </button>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>
