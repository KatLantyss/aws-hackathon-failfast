<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchVessels } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import FathometerGauge from '@/components/FathometerGauge.vue'
import DataSourceTag from '@/components/DataSourceTag.vue'
import type { VesselSummary } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import { speedLossColor, URGENCY_LABEL, URGENCY_COLOR, formatUsd } from '@/utils/format'

const router = useRouter()
const { data: vessels, state } = useAsyncData(() => true, fetchVessels)

const dsTable: DataSourceInfo = {
  status: 'real',
  endpoint: 'GET /api/v1/fleet/summary',
  description: '整張表格與展開列全部來自單一 fleet/summary 呼叫（per_vessel 陣列），沒有額外前端計算——盤點的 9 個頁面中還原度最高的一頁。',
  fields: [
    { ui: '船型', source: 'ship_class', note: '缺值時才 fallback 用前端寫死的 W1_SHIPS/W2_SHIPS 陣列猜測' },
    { ui: 'Speed Loss % / 趨勢', source: 'recent_90d_slip_pct（或 avg_slip_pct）/ slip_trend' },
    { ui: '平均油耗 / RPM / SFOC / 負載率', source: 'avg_consumption_mt / avg_rpm / avg_sfoc / avg_load_pct' },
    { ui: '距上次清洗 / 拋光 (天)', source: 'days_since_hull_clean / days_since_prop_polish' },
    { ui: '超額成本 (USD/天)', source: 'excess_fuel_cost_usd_per_day' },
    { ui: '急迫度', source: 'urgency' },
    { ui: 'TEU 容量 / 建造年份 / 船旗 / 主機型號', source: '無對應欄位，資料集不含船舶靜態規格，型別上保留但畫面未渲染' },
  ],
}

// ── Filters ───────────────────────────────────────────────────────────────────
const typeFilter = ref('all')
const keyword    = ref('')

const vesselTypes = computed(() => {
  if (!vessels.value) return []
  return Array.from(new Set(vessels.value.map((v) => v.shipClass))).sort()
})

// ── Sort ──────────────────────────────────────────────────────────────────────
type SortField =
  | 'name' | 'shipClass' | 'speedLossPct' | 'slipTrend'
  | 'avgConsumptionMt' | 'avgRpm' | 'daysSinceHullClean'
  | 'daysSincePropPolish' | 'excessFuelCostUsdMtd' | 'maintenanceUrgency'
  | 'totalRecords' | 'totalMaintEvents'

const sortField = ref<SortField>('speedLossPct')
const sortDir   = ref<'asc' | 'desc'>('desc')

const urgencyRank: Record<string, number> = { HIGH: 3, MEDIUM: 2, LOW: 1 }

function toggleSort(field: SortField) {
  if (sortField.value === field) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortDir.value   = 'desc'
  }
}

function sortIcon(field: SortField) {
  if (sortField.value !== field) return ' ⇅'
  return sortDir.value === 'asc' ? ' ▲' : ' ▼'
}

// ── Filtered + sorted data ────────────────────────────────────────────────────
const rows = computed<VesselSummary[]>(() => {
  if (!vessels.value) return []

  const filtered = vessels.value.filter((v) => {
    if (typeFilter.value !== 'all' && v.shipClass !== typeFilter.value) return false
    if (keyword.value && !v.name.toLowerCase().includes(keyword.value.toLowerCase())) return false
    return true
  })

  return [...filtered].sort((a, b) => {
    let aVal: number | string, bVal: number | string
    switch (sortField.value) {
      case 'maintenanceUrgency':
        aVal = urgencyRank[a.maintenanceUrgency] ?? 0
        bVal = urgencyRank[b.maintenanceUrgency] ?? 0
        break
      case 'slipTrend':
        aVal = a.slipTrend ?? 0
        bVal = b.slipTrend ?? 0
        break
      case 'daysSincePropPolish':
        aVal = a.daysSincePropPolish ?? 0
        bVal = b.daysSincePropPolish ?? 0
        break
      default:
        aVal = (a as any)[sortField.value] ?? 0
        bVal = (b as any)[sortField.value] ?? 0
    }
    if (typeof aVal === 'string') return sortDir.value === 'asc'
      ? aVal.localeCompare(bVal as string)
      : (bVal as string).localeCompare(aVal)
    return sortDir.value === 'asc' ? aVal - (bVal as number) : (bVal as number) - aVal
  })
})

// ── Expand ────────────────────────────────────────────────────────────────────
const expandedImo = ref<string | null>(null)

function toggleExpand(imo: string) {
  expandedImo.value = expandedImo.value === imo ? null : imo
}

function goToVessel(imo: string) {
  router.push(`/vessels/${imo}/overview`)
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function trendArrow(trend: number | null): string {
  if (trend == null) return '—'
  if (trend >  0.3) return '↑'
  if (trend < -0.3) return '↓'
  return '→'
}
function trendColor(trend: number | null): string {
  if (trend == null) return 'var(--color-ink-muted)'
  if (trend >  0.3) return 'var(--color-signal-red)'
  if (trend < -0.3) return 'var(--color-fathom-teal)'
  return 'var(--color-ink-muted)'
}
function cleanDayColor(days: number): string {
  if (days > 730) return 'var(--color-signal-red)'
  if (days > 365) return 'var(--color-brass-amber)'
  return 'var(--color-ink-muted)'
}
</script>

<template>
  <div class="mx-auto max-w-[1440px] px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4">
    <div>
      <p class="eyebrow mb-1.5">LIST-01 · Fleet Register</p>
      <h1 class="text-[1.9rem] leading-none">船隊列表</h1>
    </div>

    <!-- Filters -->
    <div class="panel p-3.5 flex flex-wrap items-center gap-4">
      <label class="flex items-center gap-2 text-sm">
        <span class="col-head">船型</span>
        <select v-model="typeFilter" class="field">
          <option value="all">全部</option>
          <option v-for="t in vesselTypes" :key="t" :value="t">{{ t }}</option>
        </select>
      </label>
      <label class="flex items-center gap-2 text-sm flex-1 min-w-[200px]">
        <span class="col-head">關鍵字</span>
        <input v-model="keyword" type="search" placeholder="船舶代號" class="field flex-1" />
      </label>
      <span class="text-xs text-[var(--color-ink-muted)] ml-auto">{{ rows.length }} 艘</span>
    </div>

    <StateDisplay v-if="state !== 'success'" :state="state === 'error' ? 'error' : 'loading'" />

    <div v-else class="panel panel--accent overflow-x-auto">
      <DataSourceTag :info="dsTable" />
      <table class="w-full text-sm" style="min-width: 1160px">
        <!-- ── Header ── -->
        <thead>
          <tr class="border-b-2" style="border-color: color-mix(in srgb, var(--color-ink-slate) 22%, transparent)">
            <th class="w-8" />
            <!-- 1 船舶代號 -->
            <th
              class="col-head text-left px-3 py-3 cursor-pointer select-none whitespace-nowrap hover:text-[var(--color-ink-slate)] transition-colors"
              @click="toggleSort('name')"
            >船舶代號{{ sortIcon('name') }}</th>
            <!-- 2 船型 -->
            <th
              class="col-head text-left px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('shipClass')"
            >船型{{ sortIcon('shipClass') }}</th>
            <!-- 日報筆數 -->
            <th
              class="col-head text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('totalRecords')"
            >日報筆數{{ sortIcon('totalRecords') }}</th>
            <!-- 養護事件數 -->
            <th
              class="col-head text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('totalMaintEvents')"
            >養護事件數{{ sortIcon('totalMaintEvents') }}</th>
            <!-- 3 Speed Loss -->
            <th
              class="col-head text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('speedLossPct')"
            >Speed Loss %{{ sortIcon('speedLossPct') }}</th>
            <!-- 4 趨勢 -->
            <th
              class="col-head text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('slipTrend')"
            >趨勢{{ sortIcon('slipTrend') }}</th>
            <!-- 5 平均油耗 -->
            <th
              class="col-head text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('avgConsumptionMt')"
            >平均油耗 (MT/天){{ sortIcon('avgConsumptionMt') }}</th>
            <!-- 6 平均 RPM -->
            <th
              class="col-head text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('avgRpm')"
            >平均 RPM{{ sortIcon('avgRpm') }}</th>
            <!-- 7 距上次清洗 -->
            <th
              class="col-head text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('daysSinceHullClean')"
            >距上次清洗 (天){{ sortIcon('daysSinceHullClean') }}</th>
            <!-- 8 距上次螺旋槳拋光 -->
            <th
              class="col-head text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('daysSincePropPolish')"
            >距上次螺旋槳拋光 (天){{ sortIcon('daysSincePropPolish') }}</th>
            <!-- 9 超額成本 -->
            <th
              class="col-head text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('excessFuelCostUsdMtd')"
            >超額成本 (USD/天){{ sortIcon('excessFuelCostUsdMtd') }}</th>
            <!-- 10 急迫度 -->
            <th
              class="col-head text-left px-3 py-3 cursor-pointer select-none whitespace-nowrap"
              @click="toggleSort('maintenanceUrgency')"
            >急迫度{{ sortIcon('maintenanceUrgency') }}</th>
          </tr>
        </thead>

        <!-- ── Body ── -->
        <tbody>
          <template v-for="v in rows" :key="v.imo">
            <tr
              class="chart-divider cursor-pointer transition-colors hover:bg-[var(--color-chart-paper-hi)]"
              @click="goToVessel(v.imo)"
            >
              <!-- expand -->
              <td class="px-2 py-2 text-center">
                <button
                  class="text-[var(--color-ink-slate)]/60 hover:text-[var(--color-ink-slate)]"
                  aria-label="展開詳情"
                  @click.stop="toggleExpand(v.imo)"
                >{{ expandedImo === v.imo ? '▾' : '▸' }}</button>
              </td>

              <!-- 1 船舶代號 -->
              <td class="px-3 py-3 font-display text-[15px] tracking-wide">{{ v.name }}</td>

              <!-- 2 船型 -->
              <td class="px-3 py-3 font-data text-xs text-[var(--color-ink-muted)]">{{ v.shipClass }}</td>

              <!-- 日報筆數 -->
              <td class="px-3 py-3 font-data text-right tabular-nums text-[var(--color-ink-muted)]">
                {{ v.totalRecords.toLocaleString() }}
              </td>

              <!-- 養護事件數 -->
              <td class="px-3 py-3 font-data text-right tabular-nums text-[var(--color-ink-muted)]">
                {{ v.totalMaintEvents ?? '—' }}
              </td>

              <!-- 3 Speed Loss -->
              <td class="px-3 py-3 text-right">
                <span
                  class="font-data font-bold tabular-nums px-1.5 py-0.5 rounded-[3px]"
                  :style="{
                    color: speedLossColor(v.speedLossPct),
                    background: `color-mix(in srgb, ${speedLossColor(v.speedLossPct)} 12%, transparent)`,
                  }"
                >{{ v.speedLossPct.toFixed(1) }}%</span>
              </td>

              <!-- 4 趨勢 -->
              <td class="px-3 py-3 font-data text-right tabular-nums">
                <span :style="{ color: trendColor(v.slipTrend) }">
                  {{ trendArrow(v.slipTrend) }}
                  <template v-if="v.slipTrend != null">
                    {{ v.slipTrend > 0 ? '+' : '' }}{{ v.slipTrend.toFixed(2) }}
                  </template>
                </span>
              </td>

              <!-- 5 平均油耗 -->
              <td class="px-3 py-3 font-data text-right tabular-nums">
                {{ v.avgConsumptionMt != null ? v.avgConsumptionMt.toFixed(1) : '—' }}
              </td>

              <!-- 6 平均 RPM -->
              <td class="px-3 py-3 font-data text-right tabular-nums text-[var(--color-ink-muted)]">
                {{ v.avgRpm != null ? v.avgRpm.toFixed(0) : '—' }}
              </td>

              <!-- 7 距上次清洗 -->
              <td class="px-3 py-3 font-data text-right tabular-nums" :style="{ color: cleanDayColor(v.daysSinceHullClean) }">
                {{ v.daysSinceHullClean }}
              </td>

              <!-- 8 距上次螺旋槳拋光 -->
              <td class="px-3 py-3 font-data text-right tabular-nums text-[var(--color-ink-muted)]">
                {{ v.daysSincePropPolish ?? '—' }}
              </td>

              <!-- 9 超額成本 -->
              <td class="px-3 py-3 font-data text-right tabular-nums text-[var(--color-signal-red)]">
                {{ formatUsd(v.excessFuelCostUsdMtd) }}
              </td>

              <!-- 10 急迫度 -->
              <td class="px-3 py-3">
                <span
                  class="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-[3px]"
                  :style="{
                    color: URGENCY_COLOR[v.maintenanceUrgency],
                    background: `color-mix(in srgb, ${URGENCY_COLOR[v.maintenanceUrgency]} 14%, transparent)`,
                  }"
                >{{ URGENCY_LABEL[v.maintenanceUrgency] }}</span>
              </td>
            </tr>

            <!-- expanded detail row -->
            <tr v-if="expandedImo === v.imo" class="chart-divider bg-black/[0.015]">
              <td colspan="13" class="px-6 py-4">
                <div class="grid grid-cols-1 md:grid-cols-[auto_1fr] gap-6 items-start">
                  <FathometerGauge
                    :value="Math.min(100, v.speedLossPct * 8)"
                    :grade="v.foulingGrade"
                    label="Speed Loss"
                    :display-value="`${v.speedLossPct.toFixed(1)}%`"
                    size="sm"
                  />
                  <div class="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2 text-xs font-data">
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">平均 STW</p>
                      <p class="tabular-nums">{{ v.avgStwKn?.toFixed(1) ?? '—' }} kt</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">平均速度 (SOG)</p>
                      <p class="tabular-nums">{{ v.avgSpeedKn?.toFixed(1) ?? '—' }} kt</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">平均 SFOC</p>
                      <p class="tabular-nums">{{ v.avgSfoc?.toFixed(0) ?? '—' }} g/kWh</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">平均負載率</p>
                      <p class="tabular-nums">{{ v.avgLoadPct?.toFixed(1) ?? '—' }} %MCR</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">平均貨載</p>
                      <p class="tabular-nums">{{ v.avgCargoOnBoardMt != null ? (v.avgCargoOnBoardMt / 1000).toFixed(0) + ' k MT' : '—' }}</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">平均吃水 (F/A)</p>
                      <p class="tabular-nums">
                        {{ v.avgForeDraftM?.toFixed(1) ?? '—' }} / {{ v.avgAftDraftM?.toFixed(1) ?? '—' }} m
                      </p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">資料期間 / 航次數</p>
                      <p class="tabular-nums">{{ v.dataSpanDays ?? '—' }} 天 / {{ v.totalVoyages }} 次</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">最後養護類型</p>
                      <p>{{ v.lastEventType ?? '—' }}</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">上次清洗類型</p>
                      <p>{{ v.lastHullCleanType ?? '—' }}</p>
                    </div>
                    <div>
                      <p class="text-[var(--color-ink-muted)] mb-0.5">全期 avg slip</p>
                      <p class="tabular-nums">{{ v.avgSlipPct?.toFixed(2) ?? '—' }} %</p>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <StateDisplay
        v-if="rows.length === 0"
        state="empty"
        empty-title="找不到符合條件的船舶"
        empty-hint="請調整篩選條件或關鍵字後再試一次。"
      />
    </div>
  </div>
</template>
