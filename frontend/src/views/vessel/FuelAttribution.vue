<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { VesselSummary } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import {
  getFuelAnomalyCause,
  getMaintenanceRecommendation,
  getSpeedLossAttribution,
  type FuelAnomalyCause,
  type SpeedLossAttributionCategory,
} from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import PanelTag from '@/components/PanelTag.vue'
import KpiCard from '@/components/KpiCard.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import { useChartTheme } from '@/composables/useChartTheme'
import { formatUsd } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data, state } = useAsyncData(() => props.imo, getFuelAnomalyCause)
const { data: maintRec } = useAsyncData(() => props.imo, getMaintenanceRecommendation)
const { data: sla, state: slaState } = useAsyncData(() => props.imo, getSpeedLossAttribution)
const chart = useChartTheme()

const SLA_CATEGORY_LABEL: Record<SpeedLossAttributionCategory, string> = {
  'hull+propeller': '船殼＋螺旋槳',
  hull: '船殼',
  propeller: '螺旋槳',
  inspection_only: '純檢查（無介入）',
  other: '其他',
}
const SLA_CATEGORY_COLOR: Record<SpeedLossAttributionCategory, string> = {
  'hull+propeller': '#A6672E',
  hull: '#E07B39',
  propeller: '#C8A84B',
  inspection_only: '#6B7A8D',
  other: '#9AA5B1',
}

const dsSlaSummary: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/speed-loss-attribution',
  description:
    'ISO 19030 框架下的 Speed Loss 船殼/螺旋槳歸因：船殼通道用 Daily FOC（同轉速燒油量，船殼阻力的真實訊號）、' +
    '螺旋槳通道用 FULL_SPD_STW_SLIP（理論前進 vs 實際前進的差），兩者物理量不同、分開估算。單一船單一養護' +
    '事件的前後快照雜訊太大（per-cycle R²≈0.07），改用「艦隊校準劣化速率」：把 12 艘訓練船的穩態日資料（風力' +
    '≤4 級、全速航行≥22 小時）依養護事件切成週期、各自對齊自己的週期基準後 pool 在一起做迴歸，得到全艦隊' +
    '共用的劣化速率（下方兩個 KPI），再套到這艘船每個養護事件距上次同類清潔的天數，回推「清潔前」的劣化量。' +
    '純檢查（UWI，無實體介入）不套用任何速率，維持「不預期改善」。',
  fields: [
    { ui: '艦隊船殼／螺旋槳劣化速率', source: 'fleet_calibration.hull / .propeller .slope_per_30d_pct（pooled regression, real）' },
    { ui: '各分類平均改善 %', source: 'summary（僅計入 physical_intervention=true 的事件, real）' },
  ],
}
const dsSlaChart: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/speed-loss-attribution',
  description:
    '每個養護事件的歸因量（正值＝改善）。船殼事件的量是「speed-loss-% (FOC-based)」、螺旋槳事件是' +
    '「slip 百分點」，兩者單位不同，不能直接疊加比大小——長條顏色只標示分類，數值請對照 metric 欄位。' +
    '灰色的純檢查事件固定為 0（不預期改善，非真的測到 0 改善）。',
  fields: [{ ui: '長條高度 / 顏色', source: 'event_attributions[].slip_delta_pct, category, metric' }],
}

const slaFleetHull = computed(() => sla.value?.fleet_calibration.hull)
const slaFleetProp = computed(() => sla.value?.fleet_calibration.propeller)

const slaSummaryEntries = computed(() => {
  if (!sla.value) return []
  return (Object.keys(sla.value.summary) as SpeedLossAttributionCategory[])
    .filter((cat) => sla.value!.summary[cat] != null)
    .map((cat) => ({ category: cat, label: SLA_CATEGORY_LABEL[cat], value: sla.value!.summary[cat] as number, color: SLA_CATEGORY_COLOR[cat] }))
})

// Bar chart: per-event delta (positive = improvement), colored by category.
// physical_intervention=false (pure UWI) events are pinned to 0 — that's a
// modeling choice (no rate applied), not an observed zero improvement.
const slaEventOption = computed(() => {
  if (!sla.value || !sla.value.event_attributions.length) return {}
  const c = chart.value
  const rows = [...sla.value.event_attributions].sort((a, b) => a.event_day - b.event_day)
  return {
    animation: false,
    grid: { left: 64, right: 32, top: 16, bottom: 60 },
    tooltip: {
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (p: any) => {
        const r = rows[p.dataIndex]
        const unit = r.metric === 'slip_pct_points' ? '個百分點 slip' : r.metric === 'speed_loss_pct_foc' ? '% speed loss (FOC)' : '—'
        return `${r.event_type} · Day ${r.event_day}<br/>分類: ${SLA_CATEGORY_LABEL[r.category]}<br/>${
          r.slip_delta_pct == null ? '無足夠資料估算' : `改善量: ${r.slip_delta_pct > 0 ? '+' : ''}${r.slip_delta_pct.toFixed(2)} ${unit}`
        }`
      },
    },
    xAxis: {
      type: 'category',
      data: rows.map((r) => `${r.event_type}\nD${r.event_day}`),
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 9, color: c.inkSlate, interval: 0 },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    yAxis: {
      type: 'value',
      name: '改善量（船殼=%speed loss／螺旋槳=slip 百分點）',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 9 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        type: 'bar',
        data: rows.map((r) => ({
          value: r.slip_delta_pct ?? 0,
          itemStyle: { color: SLA_CATEGORY_COLOR[r.category], opacity: r.physical_intervention ? 1 : 0.35 },
        })),
        barMaxWidth: 28,
      },
    ],
  }
})

const RECOMMENDED_ACTION_LABEL: Record<'UWC' | 'PP' | 'UWC+PP', string> = {
  UWC: '船殼清洗（UWC）',
  PP: '螺旋槳拋光（PP）',
  'UWC+PP': '船殼清洗＋螺旋槳拋光（UWC+PP）',
}

const dsSummary: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/fuel-anomaly-cause',
  description:
    '逐日油耗異常根因分類：先用只看操作條件（轉速/船速/吃水/載重/天氣）的模型算出「預期油耗」，' +
    '實際與預期差距超過門檻視為異常，再用 SHAP 拆解出船殼/螺旋槳/天候各自的貢獻，取最大的當主因。' +
    '完整方法與驗證見 notebooks/anomaly_analysis.ipynb §6-9。船殼/螺旋槳汙損能靠排程維護（清船殼、' +
    '拋光螺旋槳）處理、天候不行，所以年化 $ 效益只計入可信、燒太多、可維修根因的天數：把這些天的' +
    '實際-預期油耗缺口平均攤到全部分析天數，年化後用中油柴油牌價＋公開匯率換算成 USD，方法與油耗' +
    '預測頁的「清潔後省下」估算一致。',
  fields: [
    { ui: '各成因天數', source: 'summary.cause_breakdown / summary.confident_cause_breakdown' },
    { ui: '基準模型 R²', source: 'baseline_model_r2' },
    { ui: '年化可維修節省 (USD)', source: 'summary.roi.annual_saving_usd_if_fixed' },
    { ui: '建議維護動作', source: 'summary.recommended_action' },
    { ui: 'DD 週期提醒', source: 'GET .../maintenance-recommendation → drydock_reminder' },
  ],
}
const dsBar: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/fuel-anomaly-cause',
  description:
    '每一天的油耗殘差 %，顏色=主因分類。半透明的長條代表 cause_model_agrees=false' +
    '（根因模型跟基準模型對這天的異常方向判斷不一致，分類不可信，僅供參考）。',
  fields: [
    { ui: '長條高度 / 顏色 / 透明度', source: 'anomalies[].residual_pct, primary_cause, cause_model_agrees' },
  ],
}
const dsTable: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/vessels/{vessel_id}/fuel-anomaly-cause',
  description: '異常明細表，anomalies[] 全欄位原樣顯示（最近 20 筆）。',
  fields: [
    { ui: '實際/預期油耗、殘差 %、主因、養護天數', source: 'anomalies[].*' },
  ],
}

// Cause color/label map
const CAUSE_COLORS: Record<FuelAnomalyCause, string> = {
  船殼汙損: '#E07B39',
  螺旋槳汙損: '#C8A84B',
  天候: '#6B7A8D',
}

const summaryEntries = computed(() => {
  if (!data.value) return []
  const total = data.value.summary.cause_breakdown
  const confident = data.value.summary.confident_cause_breakdown
  return (Object.keys(total) as FuelAnomalyCause[])
    .map((cause) => ({
      cause,
      color: CAUSE_COLORS[cause] ?? '#6B7A8D',
      count: total[cause] ?? 0,
      confidentCount: confident[cause] ?? 0,
    }))
    .sort((a, b) => b.count - a.count)
})

// Bar chart: residual_pct per anomaly day, colored by primary_cause
const anomalyBarOption = computed(() => {
  if (!data.value || !data.value.anomalies.length) return {}
  const c = chart.value
  const rows = [...data.value.anomalies].sort((a, b) => a.noon_day - b.noon_day)
  return {
    animation: false,
    grid: { left: 64, right: 32, top: 16, bottom: 60 },
    tooltip: {
      backgroundColor: c.marineNavy,
      textStyle: { color: c.chartPaperHi, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      formatter: (p: any) => {
        const r = rows[p.dataIndex]
        const confidence = r.cause_model_agrees === false ? '（低信心）' : ''
        return `Day ${r.noon_day}<br/>實際 ${r.daily_foc_actual} MT/day → 預期 ${r.daily_foc_expected} MT/day<br/>殘差: ${r.residual_pct > 0 ? '+' : ''}${r.residual_pct.toFixed(1)}%<br/>主因: ${r.primary_cause ?? '—'}${confidence}`
      },
    },
    xAxis: {
      type: 'category',
      data: rows.map((r) => `D${r.noon_day}`),
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 9, color: c.inkSlate, interval: 0, rotate: 45 },
      axisLine: { lineStyle: { color: c.axisLine } },
    },
    yAxis: {
      type: 'value',
      name: '油耗殘差 %',
      nameTextStyle: { fontFamily: 'IBM Plex Mono', fontSize: 10 },
      axisLabel: { fontFamily: 'IBM Plex Mono', fontSize: 10, color: c.inkSlate },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        type: 'bar',
        data: rows.map((r) => ({
          value: r.residual_pct,
          itemStyle: {
            color: r.primary_cause ? CAUSE_COLORS[r.primary_cause] ?? c.fathomTeal : c.fathomTeal,
            opacity: r.cause_model_agrees === false ? 0.35 : 1,
          },
        })),
        barMaxWidth: 20,
      },
    ],
  }
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- ═══ Speed Loss 歸因（ISO 19030：船殼 vs 螺旋槳） ═══ -->
    <StateDisplay
      v-if="slaState !== 'success'"
      :state="slaState === 'error' ? 'error' : slaState === 'empty' ? 'empty' : 'loading'"
      empty-title="此船尚無 Speed Loss 歸因資料"
    />
    <template v-else-if="sla">
      <div class="panel p-4">
        <DataSourceTag :info="dsSlaSummary" />
        <PanelTag code="SLA-1" class="mb-3" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">
          Speed Loss 歸因：多少 % 的效能損失來自船殼汙損、多少來自螺旋槳汙損（艦隊校準劣化速率模型，{{ sla.fleet_calibration.calibrated_on_vessels }} 艘訓練船）
        </p>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <KpiCard
            code="SLA-1a"
            label="艦隊船殼劣化速率"
            :value="slaFleetHull?.slope_per_30d_pct ?? 0"
            :formatter="(n) => `${n.toFixed(3)} %／30 天`"
            :sublabel="slaFleetHull ? `t=${slaFleetHull.t_stat?.toFixed(2)}，n=${slaFleetHull.n_records}${slaFleetHull.significant ? '（統計顯著）' : ''}` : undefined"
            tone="red"
          />
          <KpiCard
            code="SLA-1b"
            label="艦隊螺旋槳劣化速率"
            :value="slaFleetProp?.slope_per_30d_pct ?? 0"
            :formatter="(n) => `${n.toFixed(3)} 百分點／30 天`"
            :sublabel="slaFleetProp ? `t=${slaFleetProp.t_stat?.toFixed(2)}，n=${slaFleetProp.n_records}${slaFleetProp.significant ? '（統計顯著）' : ''}` : undefined"
            tone="amber"
          />
        </div>
        <div v-if="slaSummaryEntries.length" class="mt-4 pt-4 border-t chart-divider grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div v-for="s in slaSummaryEntries" :key="s.category" class="panel p-3 border-l-4" :style="{ borderLeftColor: s.color }">
            <p class="font-display text-xs text-[var(--color-ink-slate)]/60 mb-1">{{ s.label }}養護事件平均改善</p>
            <p class="font-data text-xl" :style="{ color: s.color }">{{ s.value > 0 ? '+' : '' }}{{ s.value.toFixed(2) }}</p>
          </div>
        </div>
      </div>

      <div v-if="sla.event_attributions.length" class="panel p-3">
        <DataSourceTag :info="dsSlaChart" />
        <PanelTag code="SLA-2" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">每次養護事件的歸因改善量（灰色半透明＝純檢查，不預期改善）</p>
        <div class="h-[280px]">
          <VChart :option="slaEventOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <div v-if="sla.event_attributions.length" class="panel p-3 overflow-x-auto">
        <PanelTag code="SLA-3" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">養護事件歸因明細</p>
        <table class="w-full text-sm min-w-[640px]">
          <thead>
            <tr class="chart-divider">
              <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">事件</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">Day</th>
              <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">分類</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">清潔前</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">清潔後</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">改善量</th>
              <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">備註</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in sla.event_attributions" :key="`${e.event_type}-${e.event_day}`" class="chart-divider hover:bg-black/[0.02]">
              <td class="px-3 py-1.5 font-data">{{ e.event_type }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ e.event_day }}</td>
              <td class="px-3 py-1.5">
                <span class="text-xs px-1.5 py-0.5 rounded-[2px] font-body" :style="{ background: `${SLA_CATEGORY_COLOR[e.category]}22`, color: SLA_CATEGORY_COLOR[e.category] }">{{ SLA_CATEGORY_LABEL[e.category] }}</span>
              </td>
              <td class="px-3 py-1.5 font-data text-right">{{ e.slip_before_pct != null ? e.slip_before_pct.toFixed(2) : '—' }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ e.slip_after_pct != null ? e.slip_after_pct.toFixed(2) : '—' }}</td>
              <td
                class="px-3 py-1.5 font-data text-right font-semibold"
                :class="e.slip_delta_pct == null ? 'text-[var(--color-ink-slate)]/30' : e.slip_delta_pct >= 0 ? 'text-[var(--color-fathom-teal)]' : 'text-[var(--color-signal-red)]'"
              >
                {{ e.slip_delta_pct != null ? `${e.slip_delta_pct >= 0 ? '+' : ''}${e.slip_delta_pct.toFixed(2)}` : '—' }}
              </td>
              <td class="px-3 py-1.5 text-xs text-[var(--color-ink-slate)]/70">{{ e.notes }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- ═══ 油耗歸因（SHAP 成因分類 + ROI） ═══ -->
    <StateDisplay
      v-if="state !== 'success'"
      :state="state === 'error' ? 'error' : state === 'empty' ? 'empty' : 'loading'"
      empty-title="此船尚無油耗歸因資料"
    />
    <template v-else-if="data">
      <!-- Summary by cause + maintainable-vs-weather ROI -->
      <div class="panel p-4">
        <DataSourceTag :info="dsSummary" />
        <PanelTag code="FUEL-A1" class="mb-3" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-3">
          近 {{ data.summary.total_days_analyzed }} 個穩態日，{{ data.summary.anomaly_days }} 天油耗異常（基準模型 R²={{ data.baseline_model_r2?.toFixed(3) ?? '—' }}）
        </p>
        <div v-if="summaryEntries.length" class="grid grid-cols-3 gap-3">
          <div v-for="s in summaryEntries" :key="s.cause" class="panel p-3 border-l-4" :style="{ borderLeftColor: s.color }">
            <p class="font-display text-xs text-[var(--color-ink-slate)]/60 mb-1">{{ s.cause }}</p>
            <p class="font-data text-xl" :style="{ color: s.color }">{{ s.count }} 天</p>
            <p class="font-mono text-[10px] text-[var(--color-ink-slate)]/50 mt-0.5">其中 {{ s.confidentCount }} 天可信</p>
          </div>
        </div>
        <p v-else class="text-sm text-[var(--color-ink-slate)]/60">近期沒有偵測到油耗異常。</p>

        <!-- 可維修（船殼+螺旋槳，上面已列出天數）vs 天候：只把可維修根因換算成 $ 效益 -->
        <div v-if="summaryEntries.length" class="mt-4 pt-4 border-t chart-divider flex flex-col md:flex-row md:items-center gap-4">
          <p class="flex-1 text-xs text-[var(--color-ink-slate)]/70">
            <span class="font-display tracking-wide text-[var(--color-ink-slate)]">可維修 vs 天候：</span>
            船殼＋螺旋槳汙損可靠排程維護處理，天候不行——年化 $ 效益只計入可信、燒太多的可維修天數，
            估計每日多燒 <strong class="font-data">{{ data.summary.roi.avg_excess_fuel_mt_per_day.toFixed(3) }} MT</strong>
            （年化約 <strong class="font-data">{{ data.summary.roi.annual_excess_fuel_mt.toFixed(1) }} MT</strong>）。
            依 {{ data.summary.roi.energy_pricing.price_source.name }}（{{ data.summary.roi.energy_pricing.price_source.status === 'fetched' ? '已取得公開牌價' : '使用 fallback 牌價' }}）
            與 USD/TWD {{ data.summary.roi.energy_pricing.exchange_rate.twd_per_usd.toFixed(2) }} 換算，
            約 <strong class="font-data">{{ formatUsd(data.summary.roi.energy_pricing.daily_saving_usd) }}/日</strong>
            （{{ data.summary.roi.energy_pricing.sea_days_per_year }} 海上天）。天候造成的異常不計入此估算。
          </p>
          <KpiCard
            code="FUEL-A1b"
            label="年化可維修節省（USD，估計）"
            :value="data.summary.roi.annual_saving_usd_if_fixed"
            :formatter="formatUsd"
            tone="red"
            class="shrink-0 md:w-64"
          />
        </div>

        <!-- 建議動作：由可信天數的船殼/螺旋槳根因分佈直接映射，DD 另走固定週期提醒 -->
        <div class="mt-4 pt-4 border-t chart-divider flex flex-col sm:flex-row sm:items-center gap-3">
          <div class="flex-1 text-xs text-[var(--color-ink-slate)]/70">
            <span class="font-display tracking-wide text-[var(--color-ink-slate)]">建議維護動作：</span>
            <template v-if="data.summary.recommended_action">
              <strong class="font-data text-[var(--color-signal-red)]">{{ RECOMMENDED_ACTION_LABEL[data.summary.recommended_action] }}</strong>
              —— 依可信天數中船殼/螺旋槳根因的分佈直接對應，不含天候。
            </template>
            <span v-else>近期沒有可信的可維修根因，暫不建議動作。</span>
          </div>
          <div
            v-if="maintRec?.drydock_reminder"
            class="text-xs px-2.5 py-1.5 rounded-[2px] font-body shrink-0"
            :class="maintRec.drydock_reminder.due
              ? 'bg-[var(--color-signal-red)]/10 text-[var(--color-signal-red)]'
              : 'bg-[var(--color-ink-slate)]/5 text-[var(--color-ink-slate)]/60'"
          >
            DD 週期提醒：距上次 DD <strong class="font-data">{{ maintRec.drydock_reminder.days_since_last_dd }}</strong> 天
            （艦隊平均 {{ maintRec.drydock_reminder.fleet_avg_dd_interval_days }} 天）
            {{ maintRec.drydock_reminder.due ? '— 已到期' : '' }}
          </div>
        </div>
      </div>

      <!-- Anomaly bar chart -->
      <div v-if="data.anomalies.length" class="panel p-3">
        <DataSourceTag :info="dsBar" />
        <PanelTag code="FUEL-A2" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">每日油耗殘差 %（顏色=主因，半透明=低信心）</p>
        <div class="h-[280px]">
          <VChart :option="anomalyBarOption" autoresize class="h-full w-full" />
        </div>
      </div>

      <!-- Anomaly details table -->
      <div v-if="data.anomalies.length" class="panel p-3 overflow-x-auto">
        <DataSourceTag :info="dsTable" />
        <PanelTag code="FUEL-A3" class="mb-2" />
        <p class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70 mb-2">異常明細（最近 {{ data.anomalies.length }} 筆）</p>
        <table class="w-full text-sm min-w-[720px]">
          <thead>
            <tr class="chart-divider">
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">Day</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">實際 MT/day</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">預期 MT/day</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">殘差 %</th>
              <th class="text-left font-display text-xs uppercase tracking-wide px-3 py-2">主因</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">距清船殼</th>
              <th class="text-right font-display text-xs uppercase tracking-wide px-3 py-2">距拋螺旋槳</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="a in data.anomalies"
              :key="a.noon_day"
              class="chart-divider hover:bg-black/[0.02]"
              :class="{ 'opacity-40': a.cause_model_agrees === false }"
            >
              <td class="px-3 py-1.5 font-data text-right">{{ a.noon_day }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ a.daily_foc_actual.toFixed(1) }}</td>
              <td class="px-3 py-1.5 font-data text-right">{{ a.daily_foc_expected.toFixed(1) }}</td>
              <td
                class="px-3 py-1.5 font-data text-right font-semibold"
                :class="a.residual_pct >= 0 ? 'text-[var(--color-signal-red)]' : 'text-[var(--color-fathom-teal)]'"
              >
                {{ a.residual_pct >= 0 ? '+' : '' }}{{ a.residual_pct.toFixed(1) }}%
              </td>
              <td class="px-3 py-1.5">
                <span
                  v-if="a.primary_cause"
                  class="text-xs px-1.5 py-0.5 rounded-[2px] font-body"
                  :style="{ background: `${CAUSE_COLORS[a.primary_cause]}22`, color: CAUSE_COLORS[a.primary_cause] }"
                >{{ a.primary_cause }}</span>
                <span v-else class="text-xs text-[var(--color-ink-slate)]/40">—</span>
                <span v-if="a.cause_model_agrees === false" class="text-[10px] text-[var(--color-ink-slate)]/40 ml-1">(低信心)</span>
              </td>
              <td class="px-3 py-1.5 font-data text-right">{{ a.days_since_hull_clean }}d</td>
              <td class="px-3 py-1.5 font-data text-right">{{ a.days_since_prop_polish }}d</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
