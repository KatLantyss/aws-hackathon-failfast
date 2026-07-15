<script setup lang="ts">
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import { fetchCorrelation, fetchRecommendation } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import { useChartTheme } from '@/composables/useChartTheme'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { formatDay, formatUsd, formatNumber, formatPct } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data, state } = useAsyncData(() => props.imo, fetchCorrelation)
const { data: advisorData } = useAsyncData(() => props.imo, fetchRecommendation)
const chart = useChartTheme()

// ─── Data-source inspector metadata (§8 of docs/frontend-backend-integration-status.html) ─
// This is the page with the heaviest frontend business logic layered on real data — most
// blocks below are 'hybrid', not 'real', even though every one of them is fed by a real API.
const FUEL_FORMULA_NOTE = '前端固定用 fuel = avgConsumption × (1 + slip%/100 × 1.8) 換算，1.8 係數是寫死常數，非模型或後端算出來的'

const dsAlert: DataSourceInfo = {
  status: 'stub',
  description: '「⚡ 預警門檻設定」滑桿是純前端 UI 狀態（ref），拖動只會即時重算下方 alertStatus 文字，不會呼叫任何 API 或存到後端 —— 重新整理頁面就重置，是互動式模擬器而非持久化設定。',
  fields: [
    { ui: 'Speed Loss 門檻 / 提前天數滑桿', source: '純前端 ref，無對應後端欄位' },
    { ui: '🚨/⚠️/✅ 狀態文字', source: '前端拿 data.optimalTiming（本身已是 hybrid 計算值，見 COR-03）再套滑桿門檻二次判斷' },
  ],
}

const dsSummaryKpis: DataSourceInfo = {
  status: 'hybrid',
  endpoint: ['GET /api/v1/vessels/{vessel_id}/speed-loss', 'GET /api/v1/vessels/{vessel_id}/maintenance-events', 'GET /api/v1/fleet/summary'],
  description: '4 張卡混合了純後端值與前端聚合值。',
  fields: [
    { ui: '養護事件數 / 平均效能改善', source: '前端從 effectivenessEvents 陣列算 length / 平均 improvementPct', note: FUEL_FORMULA_NOTE },
    { ui: '目前超額成本（USD/天）', source: 'vessel.excessFuelCostUsdMtd（fleet/summary，真正的後端值）' },
    { ui: '異常事件數', source: '前端門檻判斷（見下方 COR-07）' },
  ],
}

const dsTimeline: DataSourceInfo = {
  status: 'hybrid',
  endpoint: ['GET /api/v1/vessels/{vessel_id}/speed-loss', 'GET /api/v1/vessels/{vessel_id}/maintenance-events'],
  description: 'Speed Loss % 曲線是後端原始資料；日油耗曲線是前端換算值，speed-loss 端點本身沒有逐日油耗欄位。',
  fields: [
    { ui: 'Speed Loss % 曲線', source: 'iso_timeline / slip_timeline（real）' },
    { ui: '日油耗 (MT) 曲線', source: FUEL_FORMULA_NOTE },
    { ui: '◆ 養護事件 / ▲ 異常事件標記', source: 'maintenance-events（real）+ 前端異常門檻判斷（hybrid，見 COR-07）' },
  ],
}

const dsCostBenefit: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/maintenance-recommendation',
  description: '成本效益模擬曲線是後端 maintenance-recommendation 端點算好的 curve[]，前端只負責繪圖，沒有二次加工。注意：右側 COR-03「最佳維修時機建議」是另一套完全獨立的前端邏輯，兩者可能給出不一致的結論。',
  fields: [
    { ui: '曲線 X/Y 座標', source: 'curve[].deferral_days / cumulative_excess_fuel_cost_usd' },
  ],
}

const dsOptimalTiming: DataSourceInfo = {
  status: 'hybrid',
  endpoint: ['GET /api/v1/vessels/{vessel_id}/speed-loss', 'GET /api/v1/fleet/summary'],
  description: '整個區塊都是前端從近 60 個 Speed Loss 資料點的斜率、寫死門檻（≥12%→Hull+PP、<4%→PP）、寫死油價 $620/MT 現場算出來的，跟左側 COR-02 的後端建議曲線是兩套獨立邏輯，可能互相矛盾。',
  fields: [
    { ui: '建議養護類型', source: '前端門檻：currentSL≥12→Hull Cleaning+PP，<4→Propeller Polishing，其餘→Hull Cleaning' },
    { ui: '急迫程度 / 建議窗口', source: '前端依 currentSL 與 daysUntilThreshold 門檻判斷' },
    { ui: '每日超額成本 / 90天節省', source: '前端用 avgConsumption × slip% × 1.8 × 寫死油價 $620/MT 換算' },
    { ui: '目前 / 閾值 SL %', source: 'currentSL 為 real 資料算出；閾值 8% 為前端寫死常數' },
  ],
}

const dsTypeBar: DataSourceInfo = {
  status: 'hybrid',
  endpoint: ['GET /api/v1/vessels/{vessel_id}/speed-loss', 'GET /api/v1/vessels/{vessel_id}/maintenance-events'],
  description: '維修類型分組與評級星數，是前端把每個事件的改善% 依類型聚合平均、再用寫死門檻（≥10%→5星 … ≥1%→2星）分級，非後端提供的排名。',
  fields: [
    { ui: '平均改善 % 長條 / 星等評級', source: '前端聚合 effectivenessEvents，門檻式打星（10/6/3/1% → 5/4/3/2星）' },
  ],
}

const dsEventTable: DataSourceInfo = {
  status: 'hybrid',
  endpoint: ['GET /api/v1/vessels/{vessel_id}/speed-loss', 'GET /api/v1/vessels/{vessel_id}/maintenance-events'],
  description: '事件明細表現在顯示「RPM正規化改善%」作為唯一的真實指標。原始改善%會受RPM變化影響（虛幻改善），而RPM正規化排除了轉速變化的干擾。',
  fields: [
    { ui: '改善% (raw FOC)', source: '前端計算：(FOC前-FOC後)/FOC前×100（會被RPM變化誤導）' },
    { ui: '改善% ✓ (RPM正規化)', source: '前端在同RPM範圍内對比FOC改善（排除轉速變化，真實維修效果）。若無足夠同RPM數據則顯示—' },
    { ui: 'SL 前→後', source: '前端對事件前後30天視窗的 slip_timeline 取平均（real資料）' },
    { ui: '前/後油耗 (MT)', source: FUEL_FORMULA_NOTE },
    { ui: '港口', source: '無對應欄位，固定顯示 "—"' },
    { ui: '❌/✅ 狀態', source: '前端基於RPM正規化改善%的異常門檻判斷（見下方COR-07）' },
  ],
}

const dsAnomaly: DataSourceInfo = {
  status: 'stub',
  description: '異常偵測完全是前端寫死的門檻規則，後端沒有任何異常偵測邏輯。',
  fields: [
    { ui: '「進塢後改善不明顯」', source: 'event_type === "DD" && improvementPct < 2（前端常數）' },
    { ui: '「螺旋槳拋光改善異常高」', source: 'event_type === "PP" && improvementPct > 18（前端常數）' },
    { ui: '「養護後效能反而下降」', source: 'improvementPct < 0（前端常數）' },
  ],
}

const dsInsight: DataSourceInfo = {
  status: 'hybrid',
  endpoint: ['GET /api/v1/vessels/{vessel_id}/speed-loss', 'GET /api/v1/fleet/summary'],
  description: 'AI 分析摘要是純前端字串模板（非真的呼叫 LLM），把 summary（hybrid）與 vessel（real）欄位代入固定句型組出來的文字。',
  fields: [
    { ui: '摘要文字', source: '前端模板字串代入 data.summary.* / vessel.avgSpeedLossPct / vessel.speedLossPct / vessel.speedLossTrend' },
  ],
}

// ─── Alert Threshold Settings ─────────────────────────────────────────────────
const alertThresholdPct = ref(8) // Speed Loss % threshold
const alertDaysBefore = ref(14) // Alert N days before reaching threshold
const alertEnabled = ref(true)

const alertStatus = computed(() => {
  if (!data.value || !alertEnabled.value) return null
  const { currentSpeedLossPct, degradationRatePerDay, daysUntilThreshold } = data.value.optimalTiming
  const customDaysUntil = degradationRatePerDay > 0
    ? Math.max(0, Math.round((alertThresholdPct.value - currentSpeedLossPct) / degradationRatePerDay))
    : 999

  if (currentSpeedLossPct >= alertThresholdPct.value) {
    return { level: 'CRITICAL' as const, message: `Speed Loss ${currentSpeedLossPct}% 已超過門檻 ${alertThresholdPct.value}%，建議立即安排維修。`, daysLeft: 0 }
  }
  if (customDaysUntil <= alertDaysBefore.value) {
    return { level: 'WARNING' as const, message: `預計 ${customDaysUntil} 天後達到門檻 ${alertThresholdPct.value}%（已進入警報區間 ${alertDaysBefore.value} 天前）。`, daysLeft: customDaysUntil }
  }
  return { level: 'OK' as const, message: `距離門檻尚有 ${customDaysUntil} 天，效能正常。`, daysLeft: customDaysUntil }
})

// ─── Timeline Chart ───────────────────────────────────────────────────────────
const timelineOption = computed(() => {
  if (!data.value) return {}
  const c = chart.value
  const timeline = data.value.timeline
  const events = data.value.events
  const allMaint = data.value.allMaintenanceEvents
  const dayList = timeline.map((t) => t.day)

  // Use ALL maintenance events for markLines (not just ones with before/after data)
  const EVENT_LABEL: Record<string, string> = {
    PP: '螺旋槳拋光',
    'UWI+PP': '檢查+拋光',
    UWC: '船殼清洗',
    'UWC+PP': '清洗+拋光',
    DD: '進塢',
    UWI: '水下檢查',
  }
  const markLines = allMaint.map((evt) => ({
    xAxis: evt.day,
    label: {
      formatter: EVENT_LABEL[evt.type] || evt.type,
      fontSize: 10,
      fontFamily: 'IBM Plex Sans',
      color: c.brassAmber,
    },
    lineStyle: {
      color: evt.type === 'DD' ? c.fathomTeal : evt.type === 'UWI' ? c.inkSlate : c.brassAmber,
      type: 'dashed' as const,
      width: evt.type === 'DD' ? 2 : 1.5,
    },
  }))

  const normalEventPoints = events
    .filter((evt) => !evt.isAnomaly)
    .map((evt) => {
      const idx = dayList.findIndex((d) => d >= evt.day)
      const fuel = idx >= 0 ? timeline[idx].fuelConsumptionMt : evt.fuelBefore
      return { value: [evt.day, fuel], evt }
    })

  const anomalyEventPoints = events
    .filter((evt) => evt.isAnomaly)
    .map((evt) => {
      const idx = dayList.findIndex((d) => d >= evt.day)
      const fuel = idx >= 0 ? timeline[idx].fuelConsumptionMt : evt.fuelBefore
      return { value: [evt.day, fuel], evt }
    })

  return {
    animation: false,
    grid: { left: 60, right: 60, top: 50, bottom: 70 },
    legend: {
      top: 0,
      textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 11, color: c.inkSlate },
      selected: { '日油耗 (MT)': true, 'Speed Loss %': true, '養護事件 ✅': true, '異常事件 ❌': true },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(24, 30, 40, 0.95)',
      borderColor: 'rgba(192, 138, 62, 0.4)',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#f0ede8', fontFamily: 'IBM Plex Sans', fontSize: 13 },
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', start: 0, end: 100, height: 20, bottom: 8 },
    ],
    xAxis: {
      type: 'value',
      name: 'Day',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    yAxis: [
      {
        type: 'value',
        name: '油耗 (MT/day)',
        nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
        axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
        splitLine: { lineStyle: { color: c.splitLine } },
      },
      {
        type: 'value',
        name: 'Speed Loss %',
        nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
        axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: (v: number) => `${v.toFixed(0)}%` },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '日油耗 (MT)',
        type: 'line',
        showSymbol: false,
        lineStyle: { color: c.fathomTeal, width: 1.5 },
        areaStyle: { color: c.fathomTeal, opacity: 0.08 },
        data: timeline.map((t) => [t.day, t.fuelConsumptionMt]),
        markLine: { symbol: 'none', data: markLines, silent: true },
      },
      {
        name: 'Speed Loss %',
        type: 'line',
        yAxisIndex: 1,
        showSymbol: false,
        lineStyle: { color: c.signalRed, width: 1.5 },
        data: timeline.map((t) => [t.day, t.speedLossPct]),
      },
      {
        name: '養護事件 ✅',
        type: 'scatter',
        symbolSize: 14,
        symbol: 'diamond',
        itemStyle: { color: c.brassAmber, borderColor: '#fff', borderWidth: 1.5 },
        data: normalEventPoints.map((p) => p.value),
        tooltip: {
          formatter: (params: { dataIndex: number }) => {
            const evt = normalEventPoints[params.dataIndex]?.evt
            if (!evt) return ''
            return `<b style="color:#fff;">${evt.type}</b><br/><span style="color:#aab4be;">Day ${evt.day}</span><br/><span style="color:#aab4be;">港口: ${evt.port}</span><br/><span style="color:#7dcea0;font-weight:600;">改善: ${evt.improvementPct}%</span><br/><span style="color:#aab4be;">油耗: ${evt.fuelBefore.toFixed(1)} → ${evt.fuelAfter.toFixed(1)} MT</span>`
          },
        },
      },
      {
        name: '異常事件 ❌',
        type: 'scatter',
        symbolSize: 16,
        symbol: 'triangle',
        itemStyle: { color: c.signalRed, borderColor: '#fff', borderWidth: 1.5 },
        data: anomalyEventPoints.map((p) => p.value),
        tooltip: {
          formatter: (params: { dataIndex: number }) => {
            const evt = anomalyEventPoints[params.dataIndex]?.evt
            if (!evt) return ''
            return `<b style="color:#f5c842;">⚠ ${evt.type} (異常)</b><br/><span style="color:#aab4be;">Day ${evt.day}</span><br/><span style="color:#aab4be;">港口: ${evt.port}</span><br/><span style="color:#e2572b;font-weight:600;">改善: ${evt.improvementPct}%</span><br/><span style="color:#f0ede8;">${evt.anomalyReason}</span>`
          },
        },
      },
    ],
  }
})

// ─── Cost-Benefit Curve (from MaintenanceAdvisor) ─────────────────────────────
const costBenefitOption = computed(() => {
  if (!advisorData.value) return {}
  const c = chart.value
  const curve = advisorData.value.curve

  return {
    animation: false,
    grid: { left: 64, right: 24, top: 24, bottom: 48 },
    legend: { top: 0, textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 11, color: c.inkSlate } },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(24, 30, 40, 0.95)',
      borderColor: 'rgba(192, 138, 62, 0.4)',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#f0ede8', fontFamily: 'IBM Plex Sans', fontSize: 13 },
      valueFormatter: (v: number) => `$${v.toLocaleString()}`,
    },
    xAxis: {
      type: 'value',
      name: '延後維修天數',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    yAxis: {
      type: 'value',
      name: 'USD',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: (v: number) => `$${(v / 1000).toFixed(0)}k` },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: '累積超額油耗成本',
        type: 'line',
        showSymbol: false,
        lineStyle: { color: c.signalRed, width: 2 },
        data: curve.map((p) => [p.deferralDays, p.cumulativeExcessFuelCostUsd]),
      },
    ],
  }
})

// ─── Effectiveness Bar Chart ──────────────────────────────────────────────────
const barOption = computed(() => {
  if (!data.value) return {}
  const c = chart.value
  const types = data.value.typeEffectiveness

  return {
    animation: false,
    grid: { left: 120, right: 40, top: 24, bottom: 32 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(24, 30, 40, 0.95)',
      borderColor: 'rgba(192, 138, 62, 0.4)',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#f0ede8', fontFamily: 'IBM Plex Sans', fontSize: 13 },
      axisPointer: { type: 'shadow' },
      formatter: (params: { name: string; value: number }[]) => {
        const t = types.find((t) => t.type === params[0].name)
        if (!t) return ''
        return `<b style="color:#fff;">${t.type}</b><br/><span style="color:#7dcea0;">平均改善: ${t.avgImprovementPct}%</span><br/><span style="color:#aab4be;">節省油耗: ${t.avgFuelImprovementMt} MT/day</span><br/><span style="color:#aab4be;">事件數: ${t.eventCount}</span>`
      },
    },
    xAxis: {
      type: 'value',
      name: '平均改善 %',
      nameLocation: 'middle',
      nameGap: 18,
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 11 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: (v: number) => `${v}%` },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    yAxis: {
      type: 'category',
      data: types.map((t) => t.type),
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 11, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    series: [{
      type: 'bar',
      data: types.map((t) => ({
        value: t.avgImprovementPct,
        itemStyle: {
          color: t.avgImprovementPct >= 8 ? c.fathomTeal : t.avgImprovementPct >= 4 ? c.brassAmber : c.signalRed,
        },
      })),
      barWidth: 24,
      label: { show: true, position: 'right', fontFamily: 'IBM Plex Mono', fontSize: 11, formatter: (p: { value: number }) => `${p.value}%` },
    }],
  }
})

// ─── Helpers ──────────────────────────────────────────────────────────────────
function stars(rating: number): string {
  return '⭐'.repeat(rating) + '☆'.repeat(5 - rating)
}
function urgencyColor(urgency: 'LOW' | 'MEDIUM' | 'HIGH'): string {
  if (urgency === 'HIGH') return 'var(--color-signal-red)'
  if (urgency === 'MEDIUM') return 'var(--color-brass-amber)'
  return 'var(--color-fathom-teal)'
}
function urgencyLabel(urgency: 'LOW' | 'MEDIUM' | 'HIGH'): string {
  if (urgency === 'HIGH') return '高 — 建議立即安排'
  if (urgency === 'MEDIUM') return '中 — 建議近期安排'
  return '低 — 依標準週期'
}
function alertLevelColor(level: 'CRITICAL' | 'WARNING' | 'OK'): string {
  if (level === 'CRITICAL') return 'var(--color-signal-red)'
  if (level === 'WARNING') return 'var(--color-brass-amber)'
  return 'var(--color-fathom-teal)'
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <StateDisplay
      v-if="state !== 'success'"
      :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
      empty-title="此船尚無維修-效能關聯資料"
    />
    <template v-else-if="data">

      <!-- ═══ Alert Threshold Settings + Status ═══ -->
      <div class="panel p-4">
        <DataSourceTag :info="dsAlert" />
        <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div class="flex items-center gap-2">
            <PanelTag code="ALT-01" />
            <p class="font-display text-sm">⚡ 預警門檻設定</p>
          </div>
          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input v-model="alertEnabled" type="checkbox" class="accent-[var(--color-brass-amber)] w-4 h-4" />
            啟用預警
          </label>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div>
            <label class="text-xs text-[var(--color-ink-slate)]/60 block mb-1">Speed Loss 門檻 (%)</label>
            <input
              v-model.number="alertThresholdPct"
              type="range"
              min="3"
              max="15"
              step="0.5"
              class="w-full accent-[var(--color-brass-amber)]"
            />
            <div class="flex justify-between text-xs font-data text-[var(--color-ink-slate)]/60 mt-1">
              <span>3%</span>
              <span class="font-bold text-[var(--color-ink-slate)]">{{ alertThresholdPct }}%</span>
              <span>15%</span>
            </div>
          </div>
          <div>
            <label class="text-xs text-[var(--color-ink-slate)]/60 block mb-1">提前幾天警報</label>
            <input
              v-model.number="alertDaysBefore"
              type="range"
              min="3"
              max="60"
              step="1"
              class="w-full accent-[var(--color-brass-amber)]"
            />
            <div class="flex justify-between text-xs font-data text-[var(--color-ink-slate)]/60 mt-1">
              <span>3天</span>
              <span class="font-bold text-[var(--color-ink-slate)]">{{ alertDaysBefore }} 天</span>
              <span>60天</span>
            </div>
          </div>
          <div class="flex items-center">
            <div
              v-if="alertStatus && alertEnabled"
              class="w-full rounded-lg p-3 text-sm font-data"
              :style="{ background: alertLevelColor(alertStatus.level) + '18', borderLeft: `4px solid ${alertLevelColor(alertStatus.level)}` }"
            >
              <p class="font-bold mb-1" :style="{ color: alertLevelColor(alertStatus.level) }">
                {{ alertStatus.level === 'CRITICAL' ? '🚨 超標警報' : alertStatus.level === 'WARNING' ? '⚠️ 預警中' : '✅ 正常' }}
              </p>
              <p class="text-xs">{{ alertStatus.message }}</p>
            </div>
            <div v-else class="text-sm text-[var(--color-ink-slate)]/50 italic">預警已關閉</div>
          </div>
        </div>
      </div>

      <!-- ═══ Summary KPIs ═══ -->
      <div class="relative grid grid-cols-2 md:grid-cols-4 gap-3">
        <DataSourceTag :info="dsSummaryKpis" />
        <div class="panel p-3 text-center">
          <p class="text-xs text-[var(--color-ink-slate)]/60">養護事件數</p>
          <p class="font-data text-2xl">{{ data.summary.totalEvents }}</p>
        </div>
        <div class="panel p-3 text-center">
          <p class="text-xs text-[var(--color-ink-slate)]/60">平均效能改善</p>
          <p class="font-data text-2xl text-[var(--color-fathom-teal)]">{{ formatPct(data.summary.avgImprovementPct) }}</p>
        </div>
        <div class="panel p-3 text-center">
          <p class="text-xs text-[var(--color-ink-slate)]/60">目前超額成本</p>
          <p class="font-data text-xl text-[var(--color-signal-red)]">{{ formatUsd(vessel.excessFuelCostUsdMtd) }}<span class="text-xs">/天</span></p>
          <p class="text-xs text-[var(--color-ink-slate)]/50">來自 DynamoDB</p>
        </div>
        <div class="panel p-3 text-center">
          <p class="text-xs text-[var(--color-ink-slate)]/60">異常事件</p>
          <p class="font-data text-2xl" :class="data.summary.anomalyCount > 0 ? 'text-[var(--color-signal-red)]' : ''">
            {{ data.summary.anomalyCount }}
          </p>
        </div>
      </div>

      <!-- ═══ Timeline Chart ═══ -->
      <div class="panel p-3">
        <DataSourceTag :info="dsTimeline" />
        <PanelTag code="COR-01" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">
          效能時序圖 — ◆ 養護事件 / ▲ 異常事件
        </p>
        <div class="h-[400px]">
          <VChart :option="timelineOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <!-- ═══ Cost-Benefit + Optimal Timing ═══ -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Cost-Benefit Curve -->
        <div class="panel p-3">
          <DataSourceTag :info="dsCostBenefit" />
          <PanelTag code="COR-02" class="mb-2" />
          <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">成本效益模擬曲線</p>
          <div class="h-[280px]">
            <VChart v-if="advisorData" :option="costBenefitOption" autoresize class="h-full w-full" />
            <div v-else class="h-full flex items-center justify-center text-sm text-[var(--color-ink-slate)]/50">載入中...</div>
          </div>
        </div>

        <!-- Optimal Timing Recommendation -->
        <div class="panel p-4 border-l-4" :style="{ borderLeftColor: urgencyColor(data.optimalTiming.urgency) }">
          <DataSourceTag :info="dsOptimalTiming" />
          <PanelTag code="COR-03" class="mb-2" />
          <p class="font-display text-sm mb-3">🔧 最佳維修時機建議</p>
          <div class="grid grid-cols-2 gap-3 mb-3">
            <div>
              <p class="text-xs text-[var(--color-ink-slate)]/60">建議養護類型</p>
              <p class="font-data text-base">{{ data.optimalTiming.recommendedAction }}</p>
            </div>
            <div>
              <p class="text-xs text-[var(--color-ink-slate)]/60">急迫程度</p>
              <p class="font-data text-base flex items-center gap-2">
                <span class="inline-block w-2.5 h-2.5 rounded-full" :style="{ background: urgencyColor(data.optimalTiming.urgency) }" />
                {{ urgencyLabel(data.optimalTiming.urgency) }}
              </p>
            </div>
            <div>
              <p class="text-xs text-[var(--color-ink-slate)]/60">建議窗口</p>
              <p class="font-data text-base" :style="{ color: urgencyColor(data.optimalTiming.urgency) }">
                {{ formatDay(data.optimalTiming.windowStartDay) }} — {{ formatDay(data.optimalTiming.windowEndDay) }}
              </p>
            </div>
            <div>
              <p class="text-xs text-[var(--color-ink-slate)]/60">每日超額成本</p>
              <p class="font-data text-base text-[var(--color-signal-red)]">{{ formatUsd(data.optimalTiming.excessFuelCostPerDayUsd) }}/day</p>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-2 mb-3">
            <div class="bg-[var(--color-ink-slate)]/5 rounded p-2 text-center">
              <p class="text-[10px] text-[var(--color-ink-slate)]/60">目前</p>
              <p class="font-data text-sm">{{ formatPct(data.optimalTiming.currentSpeedLossPct) }}</p>
            </div>
            <div class="bg-[var(--color-ink-slate)]/5 rounded p-2 text-center">
              <p class="text-[10px] text-[var(--color-ink-slate)]/60">閾值</p>
              <p class="font-data text-sm">{{ formatPct(data.optimalTiming.optimalThresholdPct) }}</p>
            </div>
            <div class="bg-[var(--color-ink-slate)]/5 rounded p-2 text-center">
              <p class="text-[10px] text-[var(--color-ink-slate)]/60">90天節省</p>
              <p class="font-data text-sm text-[var(--color-fathom-teal)]">{{ formatUsd(data.optimalTiming.projectedSavingsUsd) }}</p>
            </div>
          </div>
          <p class="text-xs text-[var(--color-ink-slate)]/70">{{ data.optimalTiming.reasoning }}</p>
        </div>
      </div>

      <!-- ═══ Effectiveness by Type ═══ -->
      <div class="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        <div class="panel p-3">
          <DataSourceTag :info="dsTypeBar" />
          <PanelTag code="COR-04" class="mb-2" />
          <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">維修類型 vs 平均改善效果</p>
          <div class="h-[200px]">
            <VChart :option="barOption" autoresize class="h-full w-full" />
          </div>
        </div>
        <div class="panel p-4">
          <DataSourceTag :info="dsTypeBar" />
          <PanelTag code="COR-05" class="mb-2" />
          <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">成本效益評級</p>
          <div class="flex flex-col gap-3">
            <div
              v-for="t in data.typeEffectiveness"
              :key="t.type"
              class="flex items-center justify-between border-b border-[var(--color-ink-slate)]/10 pb-2 last:border-0"
            >
              <div>
                <p class="font-data text-sm">{{ t.type }}</p>
                <p class="text-xs text-[var(--color-ink-slate)]/60">{{ t.eventCount }} 次</p>
              </div>
              <div class="text-right">
                <p class="text-sm">{{ stars(t.rating) }}</p>
                <p class="font-data text-xs text-[var(--color-fathom-teal)]">{{ formatPct(t.avgImprovementPct) }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Event Details Table ═══ -->
      <div class="panel p-4">
        <DataSourceTag :info="dsEventTable" />
        <PanelTag code="COR-06" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">養護事件效益驗證明細</p>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-[var(--color-ink-slate)]/20 text-left text-xs text-[var(--color-ink-slate)]/60">
                <th class="py-2 pr-3">Day</th>
                <th class="py-2 pr-3">類型</th>
                <th class="py-2 pr-3">港口</th>
                <th class="py-2 pr-3 text-right">前 (MT)</th>
                <th class="py-2 pr-3 text-right">後 (MT)</th>
                <th class="py-2 pr-3 text-right">改善 %<br/><span class="text-[10px]">raw FOC</span></th>
                <th class="py-2 pr-3 text-right text-[var(--color-fathom-teal)] font-bold">改善 % ✓<br/><span class="text-[10px] font-normal">RPM正規化</span></th>
                <th class="py-2 pr-3 text-right">SL 前→後</th>
                <th class="py-2 pr-3 text-center">狀態</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="evt in data.events"
                :key="evt.id"
                class="border-b border-[var(--color-ink-slate)]/8 hover:bg-[var(--color-ink-slate)]/5 transition-colors"
                :class="{ 'bg-[var(--color-signal-red)]/5': evt.isAnomaly }"
              >
                <td class="py-2 pr-3 font-data whitespace-nowrap">{{ formatDay(evt.day) }}</td>
                <td class="py-2 pr-3 whitespace-nowrap">{{ evt.type }}</td>
                <td class="py-2 pr-3 whitespace-nowrap">{{ evt.port }}</td>
                <td class="py-2 pr-3 text-right font-data">{{ formatNumber(evt.fuelBefore, 1) }}</td>
                <td class="py-2 pr-3 text-right font-data">{{ formatNumber(evt.fuelAfter, 1) }}</td>
                <td class="py-2 pr-3 text-right font-data text-[var(--color-ink-slate)]/50" :title="'Raw FOC comparison (affected by RPM change)'">
                  {{ evt.improvementPct > 0 ? '↓' : '↑' }} {{ formatPct(Math.abs(evt.improvementPct)) }}
                </td>
                <td class="py-2 pr-3 text-right font-data font-bold" :class="evt.rpmNormalizedImprovementPct ? (evt.rpmNormalizedImprovementPct > 0 ? 'text-[var(--color-fathom-teal)]' : 'text-[var(--color-signal-red)]') : 'text-[var(--color-ink-slate)]/30'" :title="'Improvement at same RPM range (true effectiveness)'">
                  {{ evt.rpmNormalizedImprovementPct !== null ? (evt.rpmNormalizedImprovementPct > 0 ? '↓' : '↑') + ' ' + formatPct(Math.abs(evt.rpmNormalizedImprovementPct)) : '—' }}
                </td>
                <td class="py-2 pr-3 text-right font-data whitespace-nowrap">
                  {{ formatNumber(evt.speedLossBefore, 1) }}% → {{ formatNumber(evt.speedLossAfter, 1) }}%
                </td>
                <td class="py-2 pr-3 text-center">
                  <span v-if="evt.isAnomaly" class="text-[var(--color-signal-red)]" :title="evt.anomalyReason ?? ''">❌</span>
                  <span v-else class="text-[var(--color-fathom-teal)]">✅</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ═══ Anomaly Alerts ═══ -->
      <div v-if="data.events.some((e) => e.isAnomaly)" class="panel p-4 border-l-4" style="border-left-color: var(--color-signal-red)">
        <DataSourceTag :info="dsAnomaly" />
        <PanelTag code="COR-07" class="mb-2" />
        <p class="font-display text-sm mb-2 text-[var(--color-signal-red)]">異常預警</p>
        <ul class="flex flex-col gap-2 text-sm">
          <li v-for="evt in data.events.filter((e) => e.isAnomaly)" :key="evt.id" class="flex gap-2">
            <span>⚠️</span>
            <span>
              <strong>{{ formatDay(evt.day) }}</strong> {{ evt.type }} @ {{ evt.port }}：{{ evt.anomalyReason }}
            </span>
          </li>
        </ul>
      </div>

      <!-- ═══ AI Insight ═══ -->
      <div class="panel p-4 border-l-4" style="border-left-color: var(--color-fathom-teal)">
        <DataSourceTag :info="dsInsight" />
        <PanelTag code="COR-08" class="mb-2" />
        <p class="font-display text-sm mb-2">AI 分析摘要</p>
        <div class="text-sm text-[var(--color-ink-slate)]/80 flex flex-col gap-2">
          <p>
            本船共記錄 <strong>{{ data.summary.totalEvents }}</strong> 次養護事件，
            平均改善效能 <strong>{{ formatPct(data.summary.avgImprovementPct) }}</strong>。
          </p>
          <p v-if="vessel.avgSpeedLossPct != null">
            近90天平均速度損失 <strong>{{ vessel.avgSpeedLossPct.toFixed(2) }}%</strong>，
            最新 <strong>{{ vessel.speedLossPct.toFixed(2) }}%</strong>
            <template v-if="vessel.speedLossTrend != null">
              （趨勢 {{ vessel.speedLossTrend > 0 ? '↑ 惡化' : '↓ 改善' }} {{ Math.abs(vessel.speedLossTrend).toFixed(2) }}%）
            </template>。
            目前超額燃油成本 <strong class="text-[var(--color-signal-red)]">{{ formatUsd(vessel.excessFuelCostUsdMtd) }}/天</strong>。
          </p>
          <p v-if="data.typeEffectiveness.length > 0">
            效果最佳：<strong>{{ data.typeEffectiveness[0].type }}</strong>
            （平均改善 {{ formatPct(data.typeEffectiveness[0].avgImprovementPct) }}）→ 高污損時優先採用。
          </p>
          <p v-if="data.typeEffectiveness.length > 1">
            效果有限：<strong>{{ data.typeEffectiveness[data.typeEffectiveness.length - 1].type }}</strong>
            （{{ formatPct(data.typeEffectiveness[data.typeEffectiveness.length - 1].avgImprovementPct) }}）→ 適合輕微污損日常維護。
          </p>
        </div>
      </div>
    </template>
  </div>
</template>
