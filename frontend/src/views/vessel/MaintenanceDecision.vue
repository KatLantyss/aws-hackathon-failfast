<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import type { VesselSummary } from '@/types/fleet'
import {
  getSpeedLossDashboard,
  getSpeedLossAttribution,
  predictFuelConsumption,
  getMaintenanceEvents,
  type BackendSpeedLossAttribution
} from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import MaintenanceRequestModal from '@/components/MaintenanceRequestModal.vue'

declare const Chart: any

const props = defineProps<{ vessel: VesselSummary; imo: string }>()

// 數據加載
const { data: slData, state: slState } = useAsyncData(() => props.imo, getSpeedLossDashboard)
const { data: attributionData } = useAsyncData(() => props.imo, getSpeedLossAttribution)
const { data: maintenanceEvents } = useAsyncData(() => props.imo, getMaintenanceEvents)

const requestModalOpen = ref(false)
const fuelPrediction = ref<any>(null)
const deferralDays = ref(180)
const costChart = ref<HTMLCanvasElement | null>(null)

// 自動觸發燃油預測
watch(slData, async () => {
  if (!slData.value?.day_max) return
  try {
    const prediction = await predictFuelConsumption({
      vessel_id: props.imo,
      noon_day: slData.value.day_max
    })
    fuelPrediction.value = prediction
  } catch (err) {
    console.error('Fuel prediction failed:', err)
  }
})

// ═══ 基於污損歸因的決策邏輯 ═══
const maintenanceRecommendation = computed(() => {
  if (!slData.value || !attributionData.value) return null

  const currentDay = slData.value.day_max
  const currentSpeedLoss = slData.value.smooth[slData.value.smooth.length - 1]?.[1] ?? 0

  // 獲取艦隊衰退率
  const hullRate = attributionData.value.fleet_calibration?.hull?.slope_per_30d_pct
  const propRate = attributionData.value.fleet_calibration?.propeller?.slope_per_30d_pct

  if (hullRate === null || propRate === null) {
    return null
  }

  // 查找最近的維修事件，計算距離上次清洗/拋光的天數
  let daysSinceHullClean = currentDay
  let daysSincePropPolish = currentDay

  if (maintenanceEvents.value) {
    for (let i = maintenanceEvents.value.events.length - 1; i >= 0; i--) {
      const event = maintenanceEvents.value.events[i]
      const eventDay = event.event_day

      if (['UWC', 'UWC+PP', 'DD'].includes(event.event_type) && daysSinceHullClean === currentDay) {
        daysSinceHullClean = currentDay - eventDay
      }

      if (['PP', 'UWI+PP', 'UWC+PP', 'DD'].includes(event.event_type) && daysSincePropPolish === currentDay) {
        daysSincePropPolish = currentDay - eventDay
      }
    }
  }

  // 計算歸因貢獻度
  const hullDegradation = (hullRate / 30) * daysSinceHullClean
  const propDegradation = (propRate / 30) * daysSincePropPolish
  const totalDegradation = hullDegradation + propDegradation

  // 維修類型對應表
  const maintenanceTypes: Record<string, any> = {
    'DD': {
      label: '進塚（Dry Dock）',
      urgency: 'CRITICAL',
      urgencyColor: 'text-red-600',
      urgencyIcon: '🚨 立即行動',
      reason: '推進系統嚴重衰退，需要全面保養',
      estimatedImprovement: 13.3,
      successRate: 90,
      estimatedCost: 350000
    },
    'UWC': {
      label: '船殼清洗 (UWC)',
      urgency: 'HIGH',
      urgencyColor: 'text-orange-600',
      urgencyIcon: '⚠️ 高優先級',
      reason: '船殼污損為主要原因，清洗可有效恢復',
      estimatedImprovement: 2.2,
      successRate: 65,
      estimatedCost: 45000
    },
    'PP': {
      label: '螺旋槳拋光 (PP)',
      urgency: 'HIGH',
      urgencyColor: 'text-orange-600',
      urgencyIcon: '⚠️ 高優先級',
      reason: '螺旋槳效率衰退為主要原因，拋光可恢復',
      estimatedImprovement: 3.0,
      successRate: 75,
      estimatedCost: 38000
    },
    'UWC+PP': {
      label: '清洗 + 拋光 (UWC+PP)',
      urgency: 'MEDIUM',
      urgencyColor: 'text-yellow-600',
      urgencyIcon: '🔶 中優先級',
      reason: '船殼和螺旋槳均有污損，複合維修應有效',
      estimatedImprovement: 2.7,
      successRate: 70,
      estimatedCost: 78000
    },
    '監控中': {
      label: '監控中',
      urgency: 'LOW',
      urgencyColor: 'text-green-600',
      urgencyIcon: '✅ 監控中',
      reason: '推進系統狀況良好，無需立即維修',
      estimatedImprovement: 0,
      successRate: 0,
      estimatedCost: 0
    }
  }

  // 決策邏輯 — 雙重檢查（推算值 + 實際 SL）
  let recommendationType = '監控中'

  // 第 1 層：實際 SL 安全檢查 — 即使推算值高，實際 SL 好也不用維修
  if (currentSpeedLoss < 10) {
    // SL 已經很好，不用維修
    recommendationType = '監控中'
  } else if (currentSpeedLoss >= 30) {
    // 極端情況：直接進塚
    recommendationType = 'DD'
  } else if (currentSpeedLoss >= 20) {
    // 第 2 層：SL 在 20-30% 之間，基於歸因分解決策
    const hullRatio = hullDegradation / totalDegradation
    const propRatio = propDegradation / totalDegradation

    if (hullRatio > 0.7 && daysSinceHullClean > 200) {
      recommendationType = 'UWC'
    } else if (propRatio > 0.7 && daysSincePropPolish > 250) {
      recommendationType = 'PP'
    } else {
      recommendationType = 'UWC+PP'
    }
  } else if (currentSpeedLoss >= 12) {
    // 第 3 層：SL 在 12-20% 之間，基於污損比例和維修距離
    const hullRatio = hullDegradation / totalDegradation
    const propRatio = propDegradation / totalDegradation

    if (hullRatio > 0.7 && daysSinceHullClean > 300) {
      recommendationType = 'UWC'
    } else if (propRatio > 0.7 && daysSincePropPolish > 350) {
      recommendationType = 'PP'
    } else if (daysSinceHullClean > 350 || daysSincePropPolish > 400) {
      recommendationType = 'UWC+PP'
    } else {
      recommendationType = '監控中'
    }
  }
  // 否則（SL < 12）→ 監控中

  const recommendation = maintenanceTypes[recommendationType]
  return recommendation ? {
    urgency: recommendation.urgency,
    urgencyColor: recommendation.urgencyColor,
    urgencyIcon: recommendation.urgencyIcon,
    recommendation: recommendation.label,
    reason: recommendation.reason,
    estimatedImprovement: recommendation.estimatedImprovement,
    successRate: recommendation.successRate,
    estimatedCost: recommendation.estimatedCost,
    type: recommendationType,
    // 歸因數據
    hullDegradation,
    propDegradation,
    totalDegradation,
    daysSinceHullClean,
    daysSincePropPolish
  } : null
})

// ═══ ROI 計算 ═══
const maintenanceRoi = computed(() => {
  if (!maintenanceRecommendation.value || !fuelPrediction.value) return null
  if (maintenanceRecommendation.value.urgency === 'LOW') return null

  const recommendation = maintenanceRecommendation.value

  const counterfactual = fuelPrediction.value.counterfactual_uwc_pp
  if (!counterfactual || !counterfactual.benefit_available) {
    return null
  }

  const dailySavingUsd = counterfactual.energy_pricing?.daily_saving_usd ?? 0
  const monthlySavings = Math.round(dailySavingUsd * 30 * (recommendation.successRate / 100))
  const annualSavings = monthlySavings * 12

  const paybackMonths = recommendation.estimatedCost > 0 && monthlySavings > 0
    ? recommendation.estimatedCost / monthlySavings
    : Infinity

  return {
    monthlySavings,
    annualSavings,
    paybackMonths: paybackMonths === Infinity ? '不划算' : Math.round(paybackMonths * 10) / 10,
    roi: recommendation.estimatedCost > 0 ? Math.round(((annualSavings - recommendation.estimatedCost / 12) / recommendation.estimatedCost * 100)) : 0,
    fuelSavingMtPerDay: counterfactual.fuel_saving_mt_per_day,
    savingPct: counterfactual.saving_pct
  }
})

// ═══ 延遲維修成本分析 ═══
const maintenanceCostAnalysis = computed(() => {
  if (!maintenanceRecommendation.value || !fuelPrediction.value) return null

  const maintenanceCost = maintenanceRecommendation.value.estimatedCost
  const counterfactual = fuelPrediction.value.counterfactual_uwc_pp

  if (!counterfactual || !counterfactual.benefit_available) return null

  // 每日油耗損失成本（單位：USD）
  // 基於燃油節省的每日金額
  const dailyFuelLossCost = counterfactual.energy_pricing?.daily_saving_usd ?? 0

  // 基於延遲天數計算累積成本
  const currentDeferralDays = deferralDays.value
  const additionalFuelCost = Math.round(dailyFuelLossCost * currentDeferralDays)
  const totalCostIfDeferred = maintenanceCost + additionalFuelCost

  return {
    maintenanceCost,
    dailyFuelLossCost,
    currentDeferralDays,
    additionalFuelCost,
    totalCostIfDeferred
  }
})

// 初始化成本圖表
const initializeCostChart = () => {
  if (!costChart.value || !maintenanceCostAnalysis.value) return

  const analysis = maintenanceCostAnalysis.value
  const maintenanceCostBase = analysis.maintenanceCost
  const fuelLossDailyRate = analysis.dailyFuelLossCost

  // 生成時間序列數據（每 15 天一個點）
  const days = []
  const maintenanceCosts = []
  const fuelLossCosts = []
  const totalCosts = []

  for (let d = 0; d <= 365; d += 15) {
    days.push(d)
    maintenanceCosts.push(maintenanceCostBase)
    const fuel = fuelLossDailyRate * d
    fuelLossCosts.push(fuel)
    totalCosts.push(maintenanceCostBase + fuel)
  }

  const ctx = costChart.value.getContext('2d')
  if (!ctx) return

  // 銷毀舊圖表
  if ((window as any).maintenanceCostChartInstance) {
    (window as any).maintenanceCostChartInstance.destroy()
  }

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark'

  ;(window as any).maintenanceCostChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: days,
      datasets: [
        {
          label: '維修成本（固定）',
          data: maintenanceCosts,
          borderColor: '#2a78d6',
          borderWidth: 2,
          backgroundColor: 'rgba(42, 120, 214, 0.05)',
          fill: true,
          tension: 0.4,
          borderDash: [5, 5],
          pointRadius: 0,
          pointHoverRadius: 6
        },
        {
          label: '累積油耗損失',
          data: fuelLossCosts,
          borderColor: '#eda100',
          borderWidth: 2,
          backgroundColor: 'rgba(237, 161, 0, 0.05)',
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 6
        },
        {
          label: '總成本',
          data: totalCosts,
          borderColor: '#e34948',
          borderWidth: 3,
          backgroundColor: 'rgba(227, 73, 72, 0.08)',
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 8
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: (v: number) => '$' + Math.round(v / 1000) + 'K'
          }
        },
        x: {
          ticks: {
            callback: (v: number) => v + '天'
          }
        }
      }
    }
  })
}

onMounted(() => {
  // 載入 Chart.js 庫
  if (typeof window !== 'undefined' && !(window as any).Chart) {
    const script = document.createElement('script')
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js'
    script.onload = () => {
      initializeCostChart()
    }
    document.head.appendChild(script)
  }
})

// 當分析數據更新時重新初始化圖表
watch(() => maintenanceCostAnalysis.value, () => {
  if ((window as any).Chart && costChart.value) {
    initializeCostChart()
  }
}, { deep: true })
</script>

<template>
  <div class="flex flex-col gap-4">
    <StateDisplay
      v-if="slState !== 'success'"
      :state="slState === 'error' ? 'error' : 'loading'"
      empty-title="載入中或無資料"
    />
    <template v-else-if="slData && maintenanceRecommendation">
      <!-- 緊急程度 -->
      <div class="panel p-4 border-l-4" :class="{
        'border-red-600 bg-red-50': maintenanceRecommendation.urgency === 'CRITICAL',
        'border-orange-600 bg-orange-50': maintenanceRecommendation.urgency === 'HIGH',
        'border-yellow-600 bg-yellow-50': maintenanceRecommendation.urgency === 'MEDIUM',
        'border-green-600 bg-green-50': maintenanceRecommendation.urgency === 'LOW'
      }">
        <p class="font-display text-sm font-semibold mb-1" :class="maintenanceRecommendation.urgencyColor">
          {{ maintenanceRecommendation.urgencyIcon }}
        </p>
        <p class="font-data text-2xl font-bold mb-1">{{ maintenanceRecommendation.recommendation }}</p>
        <p class="text-sm text-[var(--color-ink-slate)]/70">{{ maintenanceRecommendation.reason }}</p>
      </div>

      <!-- 污損歸因分解 - 簡潔風格 -->
      <div v-if="attributionData" class="panel p-4 border-l-2 border-[var(--color-fathom-teal)]">
        <p class="font-display text-sm font-semibold tracking-wide mb-4 uppercase">🔍 污損歸因</p>

        <!-- 三欄網格：艦隊速率 | 累積量 | 比例 -->
        <div class="grid grid-cols-3 gap-4 mb-4">
          <!-- 左：艦隊衰退率 -->
          <div>
            <p class="font-display text-xs text-[var(--color-ink-muted)] tracking-[0.08em] mb-2 uppercase">艦隊衰退率</p>
            <div class="space-y-1">
              <p class="text-xs text-[var(--color-ink-slate)]">
                <span class="text-[var(--color-signal-red)] font-semibold">●</span> 船殼 FOC
              </p>
              <p class="font-data text-lg font-semibold text-[var(--color-signal-red)]">
                {{ (attributionData.fleet_calibration.hull.slope_per_30d_pct ?? 0).toFixed(2) }}%
              </p>
              <p class="text-xs text-[var(--color-ink-muted)] mb-2">/30天</p>

              <p class="text-xs text-[var(--color-ink-slate)]">
                <span class="text-[var(--color-brass-amber)] font-semibold">●</span> 螺旋槳 Slip
              </p>
              <p class="font-data text-lg font-semibold text-[var(--color-brass-amber)]">
                {{ (attributionData.fleet_calibration.propeller.slope_per_30d_pct ?? 0).toFixed(2) }}%
              </p>
              <p class="text-xs text-[var(--color-ink-muted)]">/30天</p>
            </div>
          </div>

          <!-- 中：當前累積 -->
          <div>
            <p class="font-display text-xs text-[var(--color-ink-muted)] tracking-[0.08em] mb-2 uppercase">當前累積</p>
            <div class="space-y-1">
              <div>
                <p class="text-xs text-[var(--color-ink-slate)] mb-0.5">
                  船殼 ({{ maintenanceRecommendation.daysSinceHullClean }}d)
                </p>
                <p class="font-data text-lg font-bold text-[var(--color-signal-red)]">
                  {{ maintenanceRecommendation.hullDegradation.toFixed(1) }}%
                </p>
              </div>
              <div class="mt-2">
                <p class="text-xs text-[var(--color-ink-slate)] mb-0.5">
                  螺旋槳 ({{ maintenanceRecommendation.daysSincePropPolish }}d)
                </p>
                <p class="font-data text-lg font-bold text-[var(--color-brass-amber)]">
                  {{ maintenanceRecommendation.propDegradation.toFixed(2) }}%
                </p>
              </div>
            </div>
          </div>

          <!-- 右：污損比例 -->
          <div>
            <p class="font-display text-xs text-[var(--color-ink-muted)] tracking-[0.08em] mb-2 uppercase">污損比例</p>
            <div class="space-y-3">
              <div>
                <div class="flex items-center justify-between mb-1">
                  <span class="text-xs text-[var(--color-ink-slate)]">船殼</span>
                  <span class="font-data text-sm font-bold text-[var(--color-signal-red)]">
                    {{ (maintenanceRecommendation.hullDegradation / maintenanceRecommendation.totalDegradation * 100).toFixed(0) }}%
                  </span>
                </div>
                <div class="h-1.5 bg-[var(--color-ink-slate)]/10 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-[var(--color-signal-red)]"
                    :style="{ width: (maintenanceRecommendation.hullDegradation / maintenanceRecommendation.totalDegradation * 100) + '%' }"
                  ></div>
                </div>
              </div>
              <div>
                <div class="flex items-center justify-between mb-1">
                  <span class="text-xs text-[var(--color-ink-slate)]">螺旋槳</span>
                  <span class="font-data text-sm font-bold text-[var(--color-brass-amber)]">
                    {{ (maintenanceRecommendation.propDegradation / maintenanceRecommendation.totalDegradation * 100).toFixed(0) }}%
                  </span>
                </div>
                <div class="h-1.5 bg-[var(--color-ink-slate)]/10 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-[var(--color-brass-amber)]"
                    :style="{ width: (maintenanceRecommendation.propDegradation / maintenanceRecommendation.totalDegradation * 100) + '%' }"
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 狀態說明 -->
        <div class="pt-3 border-t border-[var(--color-ink-slate)]/10 text-xs text-[var(--color-ink-muted)]">
          <p>基於艦隊衰退規律計算，實際污損程度與當前 Speed Loss 相結合判斷。</p>
        </div>
      </div>

      <!-- 預期效益 -->
      <div class="panel p-4 border-l-2 border-[var(--color-fathom-teal)]">
        <p class="font-display text-sm font-semibold mb-3">📊 預期效益</p>
        <div class="grid grid-cols-3 gap-3">
          <div>
            <p class="text-xs text-[var(--color-ink-slate)]/60 mb-1">預期改善</p>
            <p class="font-data text-xl text-[var(--color-fathom-teal)] font-bold">{{ maintenanceRecommendation.estimatedImprovement.toFixed(1) }}%</p>
          </div>
          <div>
            <p class="text-xs text-[var(--color-ink-slate)]/60 mb-1">歷史成功率</p>
            <p class="font-data text-xl font-bold">{{ maintenanceRecommendation.successRate.toFixed(1) }}%</p>
          </div>
          <div>
            <p class="text-xs text-[var(--color-ink-slate)]/60 mb-1">估計成本</p>
            <p class="font-data text-xl font-bold">${{ (maintenanceRecommendation.estimatedCost / 1000).toFixed(0) }}K</p>
          </div>
        </div>
      </div>

      <!-- 維修延遲成本分析 -->
      <div v-if="maintenanceCostAnalysis" class="panel p-4 border-l-2 border-[var(--color-brass-amber)]">
        <p class="font-display text-sm font-semibold mb-4">⏱️ 維修延遲成本分析</p>

        <!-- 成本指標卡 -->
        <div class="grid grid-cols-4 gap-3 mb-4">
          <div class="bg-[var(--color-ink-slate)]/5 rounded p-3">
            <p class="text-xs text-[var(--color-ink-slate)]/60 mb-1">維修成本</p>
            <p class="font-data text-lg font-bold">${{ (maintenanceCostAnalysis.maintenanceCost / 1000).toFixed(0) }}K</p>
          </div>
          <div class="bg-[var(--color-ink-slate)]/5 rounded p-3">
            <p class="text-xs text-[var(--color-ink-slate)]/60 mb-1">延遲天數</p>
            <p class="font-data text-lg font-bold">{{ maintenanceCostAnalysis.currentDeferralDays }} 天</p>
          </div>
          <div class="bg-[var(--color-ink-slate)]/5 rounded p-3">
            <p class="text-xs text-[var(--color-ink-slate)]/60 mb-1">額外油耗成本</p>
            <p class="font-data text-lg font-bold text-[var(--color-brass-amber)]">${{ (maintenanceCostAnalysis.additionalFuelCost / 1000).toFixed(0) }}K</p>
          </div>
          <div class="bg-[var(--color-signal-red)]/10 rounded p-3 border border-[var(--color-signal-red)]/30">
            <p class="text-xs text-[var(--color-ink-slate)]/60 mb-1">總成本增加</p>
            <p class="font-data text-lg font-bold text-[var(--color-signal-red)]">${{ (maintenanceCostAnalysis.totalCostIfDeferred / 1000).toFixed(0) }}K</p>
          </div>
        </div>

        <!-- 延遲天數滑塊 -->
        <div class="mb-4">
          <label class="text-sm text-[var(--color-ink-slate)]/70 block mb-2">
            調整延遲時間：<span class="font-data font-bold">{{ maintenanceCostAnalysis.currentDeferralDays }}</span> 天
          </label>
          <input
            v-model.number="deferralDays"
            type="range"
            min="0"
            max="365"
            step="15"
            class="w-full"
          />
        </div>

        <!-- 成本圖表 -->
        <div class="mb-4" style="position: relative; height: 240px;">
          <canvas ref="costChart"></canvas>
        </div>

        <!-- 圖例 -->
        <div class="mb-4 flex gap-6 text-xs">
          <span class="flex items-center gap-2">
            <span class="w-4 h-0.5 bg-blue-500" style="border-top: 2px dashed #2a78d6;"></span>
            <span class="text-[var(--color-ink-slate)]/70">維修成本</span>
          </span>
          <span class="flex items-center gap-2">
            <span class="w-4 h-0.5 bg-amber-500"></span>
            <span class="text-[var(--color-ink-slate)]/70">油耗損失</span>
          </span>
          <span class="flex items-center gap-2">
            <span class="w-4 h-1 bg-red-500"></span>
            <span class="text-[var(--color-ink-slate)]/70">總成本</span>
          </span>
        </div>

        <!-- 成本說明 -->
        <div class="pt-3 border-t border-[var(--color-ink-slate)]/10 text-xs text-[var(--color-ink-slate)]/60 space-y-1">
          <p>💡 <strong>即時維修：</strong>${{ (maintenanceCostAnalysis.maintenanceCost / 1000).toFixed(0) }}K（固定成本）</p>
          <p>⏱️ <strong>延遲維修：</strong>${{ (maintenanceCostAnalysis.maintenanceCost / 1000).toFixed(0) }}K + 累積油耗損失</p>
          <p>延遲時間越長，Speed Loss 持續惡化，燃油消耗增加，損失成本累積。當延遲超過 {{ Math.ceil(maintenanceCostAnalysis.maintenanceCost / maintenanceCostAnalysis.dailyFuelLossCost) }} 天時，額外成本將超過維修本身。</p>
        </div>
      </div>

      <!-- ROI 分析 -->
      <div v-if="maintenanceRoi" class="panel p-4 border-l-4 border-[var(--color-signal-red)] bg-[var(--color-signal-red)]/[0.08]">
        <p class="font-display text-sm font-semibold mb-4">💰 投資回報分析</p>
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-sm text-[var(--color-ink-slate)]/70">燃油節省比例：</span>
            <span class="font-data text-lg font-bold text-[var(--color-fathom-teal)]">{{ maintenanceRoi.savingPct ? maintenanceRoi.savingPct.toFixed(1) : '—' }}%</span>
          </div>

          <div class="flex items-center justify-between">
            <span class="text-sm text-[var(--color-ink-slate)]/70">月度節省 (USD)：</span>
            <span class="font-data text-lg font-bold text-[var(--color-fathom-teal)]">${{ maintenanceRoi.monthlySavings.toLocaleString() }}</span>
          </div>

          <div class="flex items-center justify-between">
            <span class="text-sm text-[var(--color-ink-slate)]/70">月度節省 (燃油)：</span>
            <span class="font-data text-lg font-bold">{{ (maintenanceRoi.fuelSavingMtPerDay * 30).toFixed(1) }} MT</span>
          </div>

          <div class="flex items-center justify-between">
            <span class="text-sm text-[var(--color-ink-slate)]/70">年度節省 (USD)：</span>
            <span class="font-data text-lg font-bold text-[var(--color-brass-amber)]">${{ maintenanceRoi.annualSavings.toLocaleString() }}</span>
          </div>

          <div class="flex items-center justify-between pt-2 border-t border-[var(--color-ink-slate)]/10">
            <span class="text-sm text-[var(--color-ink-slate)]/70">回本週期：</span>
            <span class="font-data text-lg font-bold">{{ maintenanceRoi.paybackMonths === '不划算' ? maintenanceRoi.paybackMonths : maintenanceRoi.paybackMonths + ' 個月' }}</span>
          </div>

          <div class="bg-white rounded-lg p-3 border-2 border-[var(--color-signal-red)] mt-2">
            <p class="text-xs text-[var(--color-ink-slate)]/60 mb-2">投資回報率</p>
            <p class="font-data text-4xl font-bold text-[var(--color-signal-red)] text-center">{{ maintenanceRoi.roi }}%</p>
          </div>
        </div>
      </div>

      <!-- 決策建議 -->
      <div class="panel p-4">
        <p class="font-display text-sm font-semibold mb-3">📋 建議行動</p>
        <ul class="space-y-2 text-sm text-[var(--color-ink-slate)]/70">
          <li v-if="maintenanceRecommendation.urgency === 'CRITICAL'" class="flex gap-2">
            <span class="text-[var(--color-signal-red)]">•</span>
            <span>應在未來 <strong>7-14 天內</strong>安排維修</span>
          </li>
          <li v-else-if="maintenanceRecommendation.urgency === 'HIGH'" class="flex gap-2">
            <span class="text-orange-600">•</span>
            <span>應在未來 <strong>30 天內</strong>安排維修</span>
          </li>
          <li v-else-if="maintenanceRecommendation.urgency === 'MEDIUM'" class="flex gap-2">
            <span class="text-yellow-600">•</span>
            <span>可在<strong>次月</strong>安排維修</span>
          </li>
          <li v-else class="flex gap-2">
            <span class="text-green-600">•</span>
            <span>繼續監控，<strong>無需立即</strong>行動</span>
          </li>
          <li class="flex gap-2">
            <span>•</span>
            <span>基於艦隊衰退規律和當前污損狀況推薦</span>
          </li>
          <li class="flex gap-2">
            <span>•</span>
            <span>查看「污損歸因分析」了解詳細分解</span>
          </li>
        </ul>
      </div>

      <!-- 申請養護按鈕 -->
      <button
        type="button"
        class="w-full border-2 border-[var(--color-brass-amber)] rounded px-4 py-2.5 text-sm font-display font-semibold uppercase tracking-wide text-[var(--color-brass-amber)] hover:bg-[var(--color-brass-amber)] hover:text-white transition-colors"
        @click="requestModalOpen = true"
      >
        申請養護
      </button>

      <MaintenanceRequestModal
        v-model:open="requestModalOpen"
        :vessel="vessel"
      />
    </template>
  </div>
</template>
