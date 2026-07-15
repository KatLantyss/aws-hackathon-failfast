<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import { getSpeedLossDashboard, type BackendSpeedLossDashboardEvent } from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import { useChartTheme } from '@/composables/useChartTheme'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data, state } = useAsyncData(() => props.imo, getSpeedLossDashboard)
const chart = useChartTheme()

// ── 事件類型顏色 / 標籤 ──────────────────────────────────────────────────────
const EVENT_COLOR: Record<string, string> = {
  DD:       '#A6672E',
  'UWC+PP': '#E07B39',
  UWC:      '#C8A84B',
  PP:       '#4A9B8E',
  'UWI+PP': '#6B9BB8',
  UWI:      '#6B7A8D',
}
const EVENT_LABEL: Record<string, string> = {
  DD:       '進塢',
  'UWC+PP': '清洗+拋光',
  UWC:      '船殼清洗',
  PP:       '螺旋槳拋光',
  'UWI+PP': '水下檢查+拋光',
  UWI:      '水下檢查（僅觀察）',
}

function eventColor(type: string) { return EVENT_COLOR[type] ?? '#888' }
function eventLabel(type: string) { return EVENT_LABEL[type] ?? type }

// 計算線性回歸線（預測衰退趨勢）
function calculateRegressionLine(data: Array<[number, number | null]>) {
  const validPoints = data.filter(([_, y]) => y !== null) as Array<[number, number]>
  if (validPoints.length < 2) return []

  const n = validPoints.length
  const sumX = validPoints.reduce((s, [x]) => s + x, 0)
  const sumY = validPoints.reduce((s, [, y]) => s + y, 0)
  const sumXY = validPoints.reduce((s, [x, y]) => s + x * y, 0)
  const sumX2 = validPoints.reduce((s, [x]) => s + x * x, 0)

  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX)
  const intercept = (sumY - slope * sumX) / n

  const minX = Math.min(...validPoints.map(([x]) => x))
  const maxX = Math.max(...validPoints.map(([x]) => x))

  return [
    [minX, intercept + slope * minX],
    [maxX, intercept + slope * maxX],
  ]
}

// ── 視圖 1：Speed Loss 趨勢圖 ─────────────────────────────────────────────────
const trendOption = computed(() => {
  if (!data.value) return {}
  const c = chart.value
  const raw    = data.value.raw
  const smooth = data.value.smooth
  const events = data.value.events

  const smoothLine = smooth.filter(s => s[1] !== null).map(s => [s[0], s[1]])
  const regressionLine = calculateRegressionLine(smooth)

  const markLineData = events.map(ev => ({
    xAxis: ev.day,
    lineStyle: { color: eventColor(ev.type), type: ev.is_uwi_only ? 'dotted' : 'dashed', width: 1.5 },
    label: {
      show: true,
      formatter: ev.type,
      color: eventColor(ev.type),
      fontSize: 9,
      fontFamily: 'IBM Plex Mono',
      position: 'insideEndTop',
    },
  }))

  return {
    animation: false,
    grid: { left: 60, right: 20, top: 16, bottom: 50 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (params: any[]) => {
        const day = params[0]?.axisValue
        const lines = params.map((p: any) =>
          `${p.seriesName}：${p.value?.[1] != null ? p.value[1].toFixed(2) + ' %' : '—'}`)
        return `Day ${day}<br/>${lines.join('<br/>')}`
      },
    },
    xAxis: {
      type: 'value', min: data.value.day_min, max: data.value.day_max,
      name: '相對天數', nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 9 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value', name: 'Speed Loss %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 9 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: '{value}%' },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: '逐日原始點',
        type: 'scatter',
        data: raw,
        symbolSize: 3,
        itemStyle: { color: c.inkSlate, opacity: 0.25 },
        z: 1,
      },
      {
        name: '滾動中位數平滑',
        type: 'line',
        data: smoothLine,
        lineStyle: { width: 2.5, color: c.fathomTeal },
        itemStyle: { color: c.fathomTeal },
        symbol: 'none',
        connectNulls: false,
        z: 3,
        markLine: { symbol: 'none', silent: false, data: markLineData },
      },
      {
        name: '衰退趨勢線 (線性回歸)',
        type: 'line',
        data: regressionLine,
        lineStyle: { width: 1.5, color: c.brassAmber, type: 'dashed' },
        itemStyle: { color: c.brassAmber },
        symbol: 'none',
        z: 2,
      },
    ],
  }
})

// ── 視圖 2：船殼/螺旋槳歸因（stacked area） ─────────────────────────────────
const attributionOption = computed(() => {
  if (!data.value) return {}
  const c = chart.value
  const smooth = data.value.smooth

  const hullData = smooth.filter(s => s[1] !== null && s[1]! > 0).map(s => [s[0], s[2]])
  const propData = smooth.filter(s => s[1] !== null && s[1]! > 0).map(s => [s[0], s[3]])

  return {
    animation: false,
    grid: { left: 60, right: 20, top: 16, bottom: 50 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (params: any[]) => {
        const day = params[0]?.axisValue
        const hull = params.find((p: any) => p.seriesName === '船殼')?.value?.[1] ?? 0
        const prop = params.find((p: any) => p.seriesName === '螺旋槳')?.value?.[1] ?? 0
        return `Day ${day}<br/>船殼：${(hull as number)?.toFixed(3)} %<br/>螺旋槳：${(prop as number)?.toFixed(3)} %<br/>合計：${((hull as number) + (prop as number)).toFixed(2)} %`
      },
    },
    xAxis: {
      type: 'value', min: data.value.day_min, max: data.value.day_max,
      name: '相對天數', nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 9 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      axisLine: { lineStyle: { color: c.axisLine } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value', name: 'Speed Loss 貢獻 %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 9 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate, formatter: '{value}%' },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: '船殼',
        type: 'line', stack: 'attribution',
        areaStyle: { color: '#E07B39', opacity: 0.65 },
        lineStyle: { width: 0 }, itemStyle: { color: '#E07B39' },
        symbol: 'none', data: hullData, connectNulls: false,
      },
      {
        name: '螺旋槳',
        type: 'line', stack: 'attribution',
        areaStyle: { color: '#4A9B8E', opacity: 0.65 },
        lineStyle: { width: 0 }, itemStyle: { color: '#4A9B8E' },
        symbol: 'none', data: propData, connectNulls: false,
      },
    ],
    legend: {
      data: ['船殼', '螺旋槳'],
      textStyle: { fontFamily: 'IBM Plex Sans', fontSize: 11, color: c.inkSlate },
      bottom: 8,
    },
  }
})

const hullPct = computed(() => data.value?.summary.hull_pct ?? 50)
const propPct = computed(() => data.value?.summary.prop_pct ?? 50)
const methodNote = computed(() => data.value?.methodology.attribution_note ?? '')

// ── 視圖 3：養護事件時序列表 ──────────────────────────────────────────────────
const sortedEvents = computed<BackendSpeedLossDashboardEvent[]>(() =>
  data.value ? [...data.value.events].sort((a, b) => a.day - b.day) : [],
)

function deltaClass(ev: BackendSpeedLossDashboardEvent) {
  if (ev.delta == null) return 'text-[var(--color-ink-slate)]/40'
  return ev.delta < 0 ? 'text-[var(--color-fathom-teal)] font-semibold' : 'text-[var(--color-signal-red)] font-semibold'
}
function deltaLabel(ev: BackendSpeedLossDashboardEvent) {
  if (ev.is_uwi_only) return '—（僅觀察）'
  if (ev.delta == null) return '資料不足'
  return `${ev.delta < 0 ? '' : '+'}${ev.delta.toFixed(2)} %`
}
function deltaArrow(ev: BackendSpeedLossDashboardEvent) {
  if (ev.delta == null || ev.is_uwi_only) return ''
  return ev.delta < 0 ? '▼ 改善' : '▲ 未改善'
}
function dataInsufficient(ev: BackendSpeedLossDashboardEvent) {
  return !ev.is_uwi_only && (ev.n_before < 3 || ev.n_after < 3)
}
function isHullEvent(type: string) { return type === 'DD' || type.includes('UWC') }
function isPropEvent(type: string) { return type === 'DD' || type.includes('PP') }
</script>

<template>
  <div class="flex flex-col gap-6">

    <!-- ══ 資料載入狀態 ══ -->
    <StateDisplay
      v-if="state !== 'success'"
      :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
      empty-title="此船尚無 Speed Loss 資料"
      empty-hint="請確認資料已上傳，或此船尚無穩態全速日紀錄。"
    />

    <template v-else-if="data">

      <!-- ══ 頁首：船型 + 資料範圍 + 全期歸因摘要 ══ -->
      <div class="panel p-4 flex flex-wrap items-center gap-4">
        <div class="flex-1 min-w-0">
          <h2 class="font-display text-base tracking-wide text-[var(--color-ink-slate)] mb-0.5">
            Speed Loss Dashboard
            <span class="ml-2 text-xs font-body text-[var(--color-ink-slate)]/50">ISO 19030 概念</span>
          </h2>
          <p class="text-xs text-[var(--color-ink-slate)]/60">
            船型 <strong class="font-data">{{ data.ship_type }}</strong>
            · 資料範圍 Day <strong class="font-data">{{ Math.round(data.day_min) }}</strong>
            ～ <strong class="font-data">{{ Math.round(data.day_max) }}</strong>
            · 有效穩態日 <strong class="font-data">{{ data.raw.length }}</strong> 筆
          </p>
        </div>
        <div class="flex items-center gap-3 shrink-0">
          <div class="text-center">
            <div class="font-data text-xl" style="color:#E07B39">{{ hullPct }}%</div>
            <div class="font-display text-[10px] tracking-wide text-[var(--color-ink-slate)]/60">船殼</div>
          </div>
          <div class="text-[var(--color-ink-slate)]/30 text-lg">vs</div>
          <div class="text-center">
            <div class="font-data text-xl" style="color:#4A9B8E">{{ propPct }}%</div>
            <div class="font-display text-[10px] tracking-wide text-[var(--color-ink-slate)]/60">螺旋槳</div>
          </div>
          <div class="text-[10px] text-[var(--color-ink-slate)]/40 ml-1">啟發式估計</div>
        </div>
      </div>

      <!-- ══════════════════════════════════════════════
           Section 1：Speed Loss 趨勢
           ══════════════════════════════════════════════ -->
      <div class="flex flex-col gap-3">
        <h3 class="font-display text-xs tracking-widest uppercase text-[var(--color-ink-slate)]/50 px-1">
          ① Speed Loss 趨勢（隨時間變化）
        </h3>
        <div class="panel p-3">
          <!-- 圖例 -->
          <div class="flex flex-wrap gap-x-5 gap-y-1 mb-3">
            <div v-for="(label, type) in EVENT_LABEL" :key="type" class="flex items-center gap-1.5 text-[10px]">
              <span class="inline-block w-3 h-0.5" :style="{ background: eventColor(type), opacity: type === 'UWI' ? 0.5 : 1 }" />
              <span class="text-[var(--color-ink-slate)]/60">{{ label }}</span>
            </div>
            <div class="flex items-center gap-1.5 text-[10px]">
              <span class="inline-block w-2 h-2 rounded-full bg-[var(--color-ink-slate)] opacity-25" />
              <span class="text-[var(--color-ink-slate)]/60">逐日原始點</span>
            </div>
            <div class="flex items-center gap-1.5 text-[10px]">
              <span class="inline-block w-4 h-0.5 bg-[var(--color-fathom-teal)]" />
              <span class="text-[var(--color-ink-slate)]/60">滾動中位數（±20 天）</span>
            </div>
          </div>
          <div class="h-[360px]">
            <VChart :option="trendOption" autoresize class="h-full w-full" />
          </div>
          <p class="mt-2 text-[10px] text-[var(--color-ink-slate)]/45 leading-relaxed">
            ⚠ SPEED_LOSS 逐日噪聲極大，禁止只看單日數值下結論，請以平滑趨勢線為判讀依據。
            S21–S23 遮蔽區間（HIDDEN/PREDICT）不含原始點，允許斷點，不插值填補。
          </p>
        </div>
      </div>

      <!-- ══════════════════════════════════════════════
           Section 2：船殼 vs 螺旋槳歸因
           ══════════════════════════════════════════════ -->
      <div class="flex flex-col gap-3">
        <h3 class="font-display text-xs tracking-widest uppercase text-[var(--color-ink-slate)]/50 px-1">
          ② 船殼 vs 螺旋槳歸因（%）
        </h3>

        <div class="grid grid-cols-2 gap-3">
          <div class="panel p-4 border-l-4" style="border-left-color:#E07B39">
            <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/60 mb-1">全期船殼貢獻佔比</p>
            <p class="font-data text-3xl" style="color:#E07B39">{{ hullPct }}<span class="text-base ml-0.5">%</span></p>
          </div>
          <div class="panel p-4 border-l-4" style="border-left-color:#4A9B8E">
            <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/60 mb-1">全期螺旋槳貢獻佔比</p>
            <p class="font-data text-3xl" style="color:#4A9B8E">{{ propPct }}<span class="text-base ml-0.5">%</span></p>
          </div>
        </div>

        <div class="panel p-3">
          <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">
            船殼（橙）vs 螺旋槳（綠）Speed Loss 貢獻 — 堆疊面積圖，僅顯示正值損失區間
          </p>
          <div class="h-[300px]">
            <VChart :option="attributionOption" autoresize class="h-full w-full" />
          </div>
          <!-- 方法論摘要 -->
          <div class="mt-3 pt-3 border-t chart-divider bg-[var(--color-ink-slate)]/[0.025] rounded-[2px] px-3 py-2.5">
            <p class="font-display text-[10px] tracking-widest uppercase text-[var(--color-ink-slate)]/45 mb-1.5">方法論摘要（啟發式估計，非物理精確解）</p>
            <p class="text-xs text-[var(--color-ink-slate)]/65 leading-relaxed mb-2">{{ methodNote }}</p>
            <ul class="text-xs text-[var(--color-ink-slate)]/55 space-y-0.5 list-disc list-inside">
              <li><strong class="font-display">船殼通道</strong>：FOC 對週期基準偏離 %（同 RPM 下多燒多少油 → 阻力增加 → 船殼汙損直接信號）</li>
              <li><strong class="font-display">螺旋槳通道</strong>：FULL_SPD_STW_SLIP 超出 p5 基準（螺旋槳每轉理論 vs 實際前進落差 → 推進效率直接量）</li>
              <li>兩通道信號均正規化至 0–1，按比例競爭分配當時的 Speed Loss</li>
              <li>hull/prop contribution = share × max(0, smooth(t))，無損失時兩項均為 0</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- ══════════════════════════════════════════════
           Section 3：養護事件時序列表
           ══════════════════════════════════════════════ -->
      <div class="flex flex-col gap-3">
        <h3 class="font-display text-xs tracking-widest uppercase text-[var(--color-ink-slate)]/50 px-1">
          ③ 養護事件時序對應（清洗前後效能變化）
        </h3>

        <div class="panel p-3">
          <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">
            各養護事件前後 ±{{ data.methodology.event_window_days }} 天 SPEED_LOSS median 對比
            <span class="ml-1 text-[var(--color-ink-slate)]/40">（n &lt; {{ data.methodology.min_n_for_delta }} 標示資料不足；UWI 僅觀察不計算）</span>
          </p>

          <p v-if="!sortedEvents.length" class="text-sm text-[var(--color-ink-slate)]/50 py-6 text-center">
            此船無養護事件紀錄
          </p>

          <div v-else class="overflow-x-auto">
            <table class="w-full text-sm min-w-[760px]">
              <thead>
                <tr class="chart-divider">
                  <th class="text-right  font-display text-xs uppercase tracking-wide px-3 py-2">Day</th>
                  <th class="text-left   font-display text-xs uppercase tracking-wide px-3 py-2">事件類型</th>
                  <th class="text-right  font-display text-xs uppercase tracking-wide px-3 py-2">事前 median</th>
                  <th class="text-right  font-display text-xs uppercase tracking-wide px-3 py-2">事後 median</th>
                  <th class="text-right  font-display text-xs uppercase tracking-wide px-3 py-2">Delta</th>
                  <th class="text-center font-display text-xs uppercase tracking-wide px-3 py-2">結果</th>
                  <th class="text-left   font-display text-xs uppercase tracking-wide px-3 py-2">船殼汙損</th>
                  <th class="text-left   font-display text-xs uppercase tracking-wide px-3 py-2">螺旋槳狀態</th>
                  <th class="text-center font-display text-xs uppercase tracking-wide px-3 py-2">空蝕</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="ev in sortedEvents"
                  :key="`${ev.type}-${ev.day}`"
                  class="chart-divider hover:bg-black/[0.02]"
                  :class="{ 'opacity-45': ev.is_uwi_only }"
                >
                  <td class="px-3 py-2 font-data text-right">{{ Math.round(ev.day) }}</td>
                  <td class="px-3 py-2">
                    <span
                      class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-[2px] font-body"
                      :style="{ background: `${eventColor(ev.type)}22`, color: eventColor(ev.type) }"
                    >{{ eventLabel(ev.type) }}</span>
                    <span v-if="isHullEvent(ev.type)" class="ml-1 text-[9px] text-[#E07B39]/60">船殼</span>
                    <span v-if="isPropEvent(ev.type)" class="ml-1 text-[9px] text-[#4A9B8E]/60">螺旋槳</span>
                  </td>
                  <td class="px-3 py-2 font-data text-right">
                    <span v-if="ev.before != null">{{ ev.before.toFixed(2) }}%</span>
                    <span v-else class="text-[var(--color-ink-slate)]/30">—</span>
                    <span class="text-[9px] text-[var(--color-ink-slate)]/35 ml-1">(n={{ ev.n_before }})</span>
                  </td>
                  <td class="px-3 py-2 font-data text-right">
                    <span v-if="ev.after != null">{{ ev.after.toFixed(2) }}%</span>
                    <span v-else class="text-[var(--color-ink-slate)]/30">—</span>
                    <span class="text-[9px] text-[var(--color-ink-slate)]/35 ml-1">(n={{ ev.n_after }})</span>
                  </td>
                  <td class="px-3 py-2 font-data text-right" :class="deltaClass(ev)">
                    {{ deltaLabel(ev) }}
                  </td>
                  <td class="px-3 py-2 text-center text-xs">
                    <span
                      v-if="!ev.is_uwi_only && ev.delta != null"
                      :class="ev.delta < 0 ? 'text-[var(--color-fathom-teal)]' : 'text-[var(--color-signal-red)]'"
                    >{{ deltaArrow(ev) }}</span>
                    <span
                      v-else-if="dataInsufficient(ev)"
                      class="text-[9px] text-[var(--color-ink-slate)]/35 px-1.5 py-0.5 border rounded-[2px]"
                    >資料不足</span>
                    <span v-else-if="ev.is_uwi_only" class="text-[9px] text-[var(--color-ink-slate)]/30">觀察</span>
                  </td>
                  <td class="px-3 py-2 text-xs text-[var(--color-ink-slate)]/70">
                    {{ ev.hull_fouling_type ?? '—' }}
                    <span v-if="ev.hull_coating_condition" class="text-[9px] text-[var(--color-ink-slate)]/40 block">塗層：{{ ev.hull_coating_condition }}</span>
                  </td>
                  <td class="px-3 py-2 text-xs text-[var(--color-ink-slate)]/70">{{ ev.propeller_condition ?? '—' }}</td>
                  <td class="px-3 py-2 text-center text-xs">
                    <span
                      v-if="ev.cavitation_found"
                      :class="ev.cavitation_found.toLowerCase() === 'yes' || ev.cavitation_found === '1'
                        ? 'text-[var(--color-signal-red)]' : 'text-[var(--color-ink-slate)]/40'"
                    >{{ ev.cavitation_found }}</span>
                    <span v-else class="text-[var(--color-ink-slate)]/30">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p class="mt-3 text-[10px] text-[var(--color-ink-slate)]/45 leading-relaxed">
            delta = 事後中位數 − 事前中位數（SPEED_LOSS %）。
            <strong>delta &lt; 0 = 效能損失下降 = 改善</strong>；delta &gt; 0 = 效能未改善。
            UWI（水下檢查）不套用改善計算，僅為觀察紀錄。
          </p>
        </div>
      </div>

    </template>
  </div>
</template>
