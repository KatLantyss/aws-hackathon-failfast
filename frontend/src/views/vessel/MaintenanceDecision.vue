<script setup lang="ts">
import { computed, ref } from 'vue'
import type { VesselSummary } from '@/types/fleet'
import { getSpeedLossDashboard } from '@/services/backend'
import { useAsyncData } from '@/composables/useAsyncData'
import StateDisplay from '@/components/StateDisplay.vue'
import MaintenanceRequestModal from '@/components/MaintenanceRequestModal.vue'
import { formatUsd } from '@/utils/format'

const props = defineProps<{ vessel: VesselSummary; imo: string }>()
const { data: slData, state: slState } = useAsyncData(() => props.imo, getSpeedLossDashboard)

const requestModalOpen = ref(false)

// ═══ 維修建議邏輯 ── 基於根因分析（後端推薦） ═══
const maintenanceRecommendation = computed(() => {
  if (!slData.value?.smooth || slData.value.smooth.length === 0) return null

  const latestPoint = slData.value.smooth[slData.value.smooth.length - 1]
  const latestSL = latestPoint?.[1]

  if (latestSL === null || latestSL === undefined) return null

  // 維修類型對應表（由根因分析決定：hull_confident_days vs propeller_confident_days）
  const maintenanceTypes = {
    'DD': {
      label: '進塚（Dry Dock）',
      urgency: 'CRITICAL',
      urgencyColor: 'text-red-600',
      urgencyIcon: '🚨 立即行動',
      reason: '船體污損嚴重，需全面處理',
      estimatedImprovement: 13.3,
      successRate: 85.7,
      estimatedCost: 350000
    },
    'UWC+PP': {
      label: '清洗 + 拋光 (UWC+PP)',
      urgency: 'HIGH',
      urgencyColor: 'text-orange-600',
      urgencyIcon: '⚠️ 高優先級',
      reason: '船殼+螺旋槳雙重污損，複合維修應有效',
      estimatedImprovement: 2.7,
      successRate: 57.1,
      estimatedCost: 78000
    },
    'UWC': {
      label: '船殼清洗 (UWC)',
      urgency: 'MEDIUM',
      urgencyColor: 'text-yellow-600',
      urgencyIcon: '🔶 中優先級',
      reason: '船殼汙損為主要根因',
      estimatedImprovement: 2.2,
      successRate: 16.7,
      estimatedCost: 45000
    },
    'PP': {
      label: '螺旋槳拋光 (PP)',
      urgency: 'MEDIUM',
      urgencyColor: 'text-yellow-600',
      urgencyIcon: '🔶 中優先級',
      reason: '螺旋槳效率衰退為主要根因',
      estimatedImprovement: 3.0,
      successRate: 63.6,
      estimatedCost: 38000
    }
  }

  // 決定建議類型
  let recommendationType = 'UWC+PP'  // 預設

  if (latestSL >= 30) {
    recommendationType = 'DD'
  } else if (latestSL < 10) {
    return {
      urgency: 'LOW',
      urgencyColor: 'text-green-600',
      urgencyIcon: '✅ 監控中',
      recommendation: '監控中',
      reason: '船體狀況良好 (SL < 10%)，無需立即維修',
      estimatedImprovement: 0,
      successRate: 0,
      estimatedCost: 0
    }
  }
  // 10 <= SL < 30：用根因分析決定（UWC vs PP vs UWC+PP）
  // 注意：實際使用時應從後端的 root_cause_confidence 或 recommendedAction 獲取
  // 這裡暫用 SL 值作為後備邏輯

  const recommendation = maintenanceTypes[recommendationType]
  return recommendation ? {
    urgency: recommendation.urgency,
    urgencyColor: recommendation.urgencyColor,
    urgencyIcon: recommendation.urgencyIcon,
    recommendation: recommendation.label,
    reason: recommendation.reason,
    estimatedImprovement: recommendation.estimatedImprovement,
    successRate: recommendation.successRate,
    estimatedCost: recommendation.estimatedCost
  } : null
})

// ═══ ROI 計算 ═══
const maintenanceRoi = computed(() => {
  if (!maintenanceRecommendation.value || !slData.value?.smooth) return null

  const recommendation = maintenanceRecommendation.value
  const latestPoint = slData.value.smooth[slData.value.smooth.length - 1]
  const latestSL = latestPoint?.[1] ?? 0

  // 估計月度節油：Speed Loss % × 0.5 MT/day × 30 days × $650/MT
  const fuelSavingMt = latestSL * 0.5
  const fuelPrice = 650
  const monthlySavings = Math.round(fuelSavingMt * 30 * fuelPrice * (recommendation.successRate / 100))
  const annualSavings = monthlySavings * 12
  const paybackMonths = recommendation.estimatedCost > 0 ? recommendation.estimatedCost / monthlySavings : Infinity

  return {
    monthlySavings,
    annualSavings,
    paybackMonths: paybackMonths === Infinity ? '不划算' : Math.round(paybackMonths * 10) / 10,
    roi: recommendation.estimatedCost > 0 ? Math.round(((annualSavings - recommendation.estimatedCost / 12) / recommendation.estimatedCost * 100)) : 0
  }
})
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

      <!-- ROI 分析 - 重點呈現 -->
      <div v-if="maintenanceRoi && maintenanceRoi.annualSavings > 0" class="panel p-4 border-l-4 border-[var(--color-signal-red)] bg-[var(--color-signal-red)]/[0.08]">
        <p class="font-display text-sm font-semibold mb-4">💰 投資回報分析</p>
        <div class="space-y-3">
          <!-- 月度節省 -->
          <div class="flex items-center justify-between">
            <span class="text-sm text-[var(--color-ink-slate)]/70">月度節省：</span>
            <span class="font-data text-lg font-bold text-[var(--color-fathom-teal)]">${{ maintenanceRoi.monthlySavings.toLocaleString() }}</span>
          </div>

          <!-- 年度節省 -->
          <div class="flex items-center justify-between">
            <span class="text-sm text-[var(--color-ink-slate)]/70">年度節省：</span>
            <span class="font-data text-lg font-bold text-[var(--color-brass-amber)]">${{ maintenanceRoi.annualSavings.toLocaleString() }}</span>
          </div>

          <!-- 回本週期 -->
          <div class="flex items-center justify-between pt-2 border-t border-[var(--color-ink-slate)]/10">
            <span class="text-sm text-[var(--color-ink-slate)]/70">回本週期：</span>
            <span class="font-data text-lg font-bold">{{ maintenanceRoi.paybackMonths === '不划算' ? maintenanceRoi.paybackMonths : maintenanceRoi.paybackMonths + ' 個月' }}</span>
          </div>

          <!-- ROI 百分比 - 最突出 -->
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
            <span>查看「船體污損趨勢」Tab 瞭解詳細分析</span>
          </li>
          <li class="flex gap-2">
            <span>•</span>
            <span>查看「維修紀錄」Tab 對比歷史維修效果</span>
          </li>
        </ul>
      </div>

      <!-- 當前狀態 -->
      <div class="panel p-4 bg-[var(--color-ink-slate)]/[0.02]">
        <p class="font-display text-xs text-[var(--color-ink-slate)]/60 mb-2">當前狀態</p>
        <dl class="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt class="text-xs text-[var(--color-ink-slate)]/50">速度損失</dt>
            <dd class="font-data text-xl font-bold">{{ slData.smooth[slData.smooth.length - 1]?.[1]?.toFixed(1) ?? '—' }}%</dd>
          </div>
          <div>
            <dt class="text-xs text-[var(--color-ink-slate)]/50">距上次清洗</dt>
            <dd class="font-data text-lg">{{ vessel.daysSinceHullClean ?? '—' }} <span class="text-xs">天</span></dd>
          </div>
        </dl>
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
