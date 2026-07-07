<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFleetStore } from '@/stores/fleetStore'
import EventDetailDialog from '@/components/history/EventDetailDialog.vue'

const fleet = useFleetStore()

const events = [
  {
    date: '2022-03-15', vessel: 'YM WELLNESS', type: '水下檢查', note: '船體中度生物附著，安排螺旋槳拋光',
    detail: '水下檢查影像顯示船體左舷與右舷吃水線附近皆有中度海生物附著，螺旋槳葉面亦有輕微附著。AI 比對近 30 日 Speed Loss 趨勢，判定污損已影響推進效率，建議安排螺旋槳拋光作業。',
    zones: [{ name: '船體左舷', severity: '中度' }, { name: '船體右舷', severity: '中度' }, { name: '螺旋槳', severity: '輕度' }]
  },
  {
    date: '2022-06-02', vessel: 'YM WELLNESS', type: '螺旋槳拋光', note: '推進效率提升約 4.2%',
    detail: '完成螺旋槳拋光作業後，AI 比對清潔前後 14 日的午報資料，推進效率明顯回升，Speed Loss 與 Daily FOC 皆同步改善，驗證本次維修作業具備實際節能效益。',
    metrics: [{ label: 'Speed Loss', before: '7.8%', after: '3.1%' }, { label: 'Daily FOC', before: '148 t/day', after: '138 t/day' }]
  },
  {
    date: '2023-02-10', vessel: 'YM MANDATE', type: '水下檢查', note: '船體輕微生物附著，暫不需清潔',
    detail: '水下檢查僅見輕微生物附著，尚未達到影響推進效率的門檻，AI 綜合近期 Speed Loss 趨勢後判定暫不需安排清潔，建議 6 個月後再次追蹤。',
    zones: [{ name: '船體左舷', severity: '輕度' }, { name: '船體右舷', severity: '輕度' }]
  },
  {
    date: '2023-09-21', vessel: 'YM CREDIBILITY', type: '水下檢查', note: '偵測螺旋槳輕微損傷',
    detail: '水下檢查影像顯示螺旋槳葉緣有輕微機械損傷痕跡，非生物附著造成。AI 判定該損傷對目前效能影響有限，但建議持續追蹤是否惡化。',
    zones: [{ name: '螺旋槳', severity: '輕度' }]
  },
  {
    date: '2024-01-18', vessel: 'YM UTMOST', type: '午報異常', note: '油耗偏高，AI 判定為海況異常，非船體問題',
    detail: 'AI 偵測到當日 Daily FOC 明顯偏高，但同日 WIND_SCALE 與浪高紀錄皆超出正常範圍，且該異常僅單日出現、未形成持續趨勢，判定為海況造成的短期油耗上升，非船體或螺旋槳效能劣化。'
  },
  {
    date: '2024-11-05', vessel: 'YM CREDIBILITY', type: '螺旋槳拋光', note: '推進效率提升約 5.8%',
    detail: '本次拋光針對 2023-09-21 檢測出的螺旋槳葉緣損傷區域進行處理，清潔後 14 日數據顯示推進效率顯著回升，驗證維修排程建議的準確性。',
    metrics: [{ label: 'Speed Loss', before: '9.4%', after: '3.6%' }, { label: 'Daily FOC', before: '182 t/day', after: '167 t/day' }]
  },
  {
    date: '2025-11-30', vessel: 'YM CREDIBILITY', type: '水下檢查', note: '偵測螺旋槳葉緣損傷，已排入下次水下清潔窗口',
    detail: '水下檢查再次於螺旋槳葉緣偵測到損傷痕跡，且船體左右舷皆有中度以上生物附著。AI 判定 Speed Loss 已進入持續惡化趨勢，已排入下次靠港的水下清潔窗口。',
    zones: [{ name: '船體左舷', severity: '中度' }, { name: '船體右舷', severity: '嚴重' }, { name: '螺旋槳', severity: '中度' }]
  },
  {
    date: '2026-04-12', vessel: 'YM WELLNESS', type: '水下檢查', note: '船體輕微生物附著，建議 3 個月內安排螺旋槳拋光',
    detail: '水下檢查顯示船體輕微生物附著，螺旋槳表面亦有輕微附著物。目前 Speed Loss 尚未達門檻，但劣化速率略高於船隊平均，建議 3 個月內安排螺旋槳拋光以避免持續惡化。',
    zones: [{ name: '船體左舷', severity: '輕度' }, { name: '螺旋槳', severity: '輕度' }]
  },
  {
    date: '2026-05-18', vessel: 'YM UTMOST', type: '午報異常', note: '油耗偏高，AI 判定為海況異常，非船體問題',
    detail: 'AI 偵測到油耗單日異常升高，但比對當日氣象紀錄顯示風力與浪況皆超出良好天氣門檻。由於異常僅發生單日且未延續，判定為海況因素而非船體效能劣化，不影響清潔排程建議。'
  },
  {
    date: '2026-06-02', vessel: 'YM MANDATE', type: '螺旋槳拋光', note: '推進效率提升約 3.1%',
    detail: '定期排程之螺旋槳拋光作業，清潔前船體與螺旋槳污損程度皆為輕度。清潔後 14 日數據顯示推進效率小幅提升，符合預期的定期保養效益。',
    metrics: [{ label: 'Speed Loss', before: '5.3%', after: '2.1%' }, { label: 'Daily FOC', before: '124 t/day', after: '117 t/day' }]
  }
].sort((a, b) => b.date.localeCompare(a.date))

const detailOpen = ref(false)
const selectedEvent = ref<(typeof events)[number] | null>(null)

function openDetail(e: (typeof events)[number]) {
  selectedEvent.value = e
  detailOpen.value = true
}

const minDate = events[events.length - 1].date
const maxDate = events[0].date

const startDate = ref(minDate)
const endDate = ref(maxDate)
const activePreset = ref<'90d' | '1y' | 'all'>('all')
const selectedVessel = ref<string>('all')
const selectedType = ref<string>('all')

const vesselOptions = computed(() => [
  { title: '全部船隻', value: 'all' },
  ...fleet.vessels.map((v) => ({ title: v.name, value: v.name }))
])

const typeOptions = computed(() => [
  { title: '全部事件類型', value: 'all' },
  ...[...new Set(events.map((e) => e.type))].map((t) => ({ title: t, value: t }))
])

const typeColor = (type: string) =>
  type === '水下檢查' ? 'primary' : type === '螺旋槳拋光' ? 'secondary' : 'warning'

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function setPreset(preset: '90d' | '1y' | 'all') {
  activePreset.value = preset
  const today = new Date()
  if (preset === 'all') {
    startDate.value = minDate
    endDate.value = maxDate
    return
  }
  const from = new Date(today)
  from.setDate(from.getDate() - (preset === '90d' ? 90 : 365))
  startDate.value = toISODate(from)
  endDate.value = toISODate(today)
}

const filteredEvents = computed(() =>
  events.filter(
    (e) =>
      e.date >= startDate.value &&
      e.date <= endDate.value &&
      (selectedVessel.value === 'all' || e.vessel === selectedVessel.value) &&
      (selectedType.value === 'all' || e.type === selectedType.value)
  )
)
</script>

<template>
  <div class="pa-6">
    <v-expansion-panels variant="accordion" class="mb-4">
      <v-expansion-panel bg-color="card" rounded="lg">
        <v-expansion-panel-title>
          <v-icon icon="mdi-database-sync-outline" color="primary" class="mr-2" />
          <span class="text-subtitle-2 font-weight-medium">資料來源與整合說明</span>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="d-flex flex-wrap align-center ga-2 mb-3">
            <div class="pipeline-step">
              <v-icon icon="mdi-file-delimited-outline" size="18" color="secondary" />
              <div>
                <div>Noon Report CSV</div>
                <div class="text-caption text-medium-emphasis">15 艘船 · 2021–2025</div>
              </div>
            </div>
            <v-icon icon="mdi-arrow-right" size="16" color="grey" />
            <div class="pipeline-step">
              <v-icon icon="mdi-cog-sync-outline" size="18" color="secondary" />
              <div>
                <div>自動清洗／單位換算</div>
                <div class="text-caption text-medium-emphasis">VLSFO 當量 · 門檻過濾</div>
              </div>
            </div>
            <v-icon icon="mdi-arrow-right" size="16" color="grey" />
            <div class="pipeline-step">
              <v-icon icon="mdi-database-outline" size="18" color="secondary" />
              <div>結構化船舶效能資料庫</div>
            </div>
            <v-icon icon="mdi-arrow-right" size="16" color="grey" />
            <div class="pipeline-step">
              <v-icon icon="mdi-view-dashboard-outline" size="18" color="secondary" />
              <div>Dashboard／報告</div>
            </div>
          </div>
          <div class="text-caption text-medium-emphasis mb-3">
            Demo 環境以每船 14 天樣本代表完整 5 年資料庫。
          </div>
          <v-alert type="info" variant="tonal" density="compact" icon="mdi-puzzle-outline">
            <span class="text-body-2">
              <strong>選配模組：</strong>水下檢查報告（PDF）自動解析。目前歷史紀錄以每日午報 CSV 為主要資料來源；若競賽現場提供水下報告 PDF，可另外掛載解析模組自動補齊污損分區與拋光前後對比，不影響核心 Speed Loss / FUEL_CONSUMP 功能運作。
            </span>
          </v-alert>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <v-sheet rounded color="card" class="pa-4" elevation="0">
      <div class="text-subtitle-2 mb-3">歷史紀錄 · 午報 / 水下檢查 / 維修事件</div>

      <div class="d-flex flex-wrap align-center ga-3 pb-3 mb-3 filter-toolbar">
        <v-select
          v-model="selectedVessel"
          :items="vesselOptions"
          label="船隻"
          density="compact"
          hide-details
          style="max-width: 180px"
        />
        <v-select
          v-model="selectedType"
          :items="typeOptions"
          label="事件類型"
          density="compact"
          hide-details
          style="max-width: 180px"
        />
        <v-text-field v-model="startDate" type="date" label="起始日期" density="compact" hide-details style="max-width: 170px" @update:model-value="activePreset = 'all' as any" />
        <span class="text-medium-emphasis">至</span>
        <v-text-field v-model="endDate" type="date" label="結束日期" density="compact" hide-details style="max-width: 170px" @update:model-value="activePreset = 'all' as any" />
        <v-chip size="small" :variant="activePreset === '90d' ? 'flat' : 'tonal'" :color="activePreset === '90d' ? 'primary' : undefined" @click="setPreset('90d')">近 90 天</v-chip>
        <v-chip size="small" :variant="activePreset === '1y' ? 'flat' : 'tonal'" :color="activePreset === '1y' ? 'primary' : undefined" @click="setPreset('1y')">近 1 年</v-chip>
        <v-chip size="small" :variant="activePreset === 'all' ? 'flat' : 'tonal'" :color="activePreset === 'all' ? 'primary' : undefined" @click="setPreset('all')">全部</v-chip>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">篩選範圍內共 {{ filteredEvents.length }} 筆事件</span>
      </div>

      <v-table density="comfortable">
        <thead>
          <tr>
            <th>日期</th>
            <th>船名</th>
            <th>事件類型</th>
            <th>AI 分析摘要</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(e, i) in filteredEvents" :key="i" class="event-row" @click="openDetail(e)">
            <td>{{ e.date }}</td>
            <td>{{ e.vessel }}</td>
            <td><v-chip size="small" :color="typeColor(e.type)" variant="tonal">{{ e.type }}</v-chip></td>
            <td class="text-medium-emphasis">{{ e.note }}</td>
            <td class="text-right">
              <v-icon icon="mdi-chevron-right" size="18" color="grey" />
            </td>
          </tr>
          <tr v-if="!filteredEvents.length">
            <td colspan="5" class="text-center text-medium-emphasis py-6">此區間內無事件紀錄</td>
          </tr>
        </tbody>
      </v-table>
    </v-sheet>

    <v-alert v-if="!fleet.vessels.length" type="info" class="mt-4">尚無歷史資料</v-alert>

    <EventDetailDialog v-model="detailOpen" :event="selectedEvent" />
  </div>
</template>

<style scoped>
.pipeline-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  font-size: 13px;
}

.filter-toolbar {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.event-row {
  cursor: pointer;
  transition: background 0.12s ease;
}

.event-row:hover {
  background: rgba(255, 255, 255, 0.04);
}
</style>
