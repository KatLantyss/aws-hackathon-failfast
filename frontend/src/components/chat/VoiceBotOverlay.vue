<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useChatContextStore } from '@/stores/chatContext'
import { resolveChatTurn } from '@/composables/useChatOrchestrator'
import { useChatVoiceInput } from '@/composables/useChatVoiceInput'
import type { ChatTurn, NluRequestBody, NluResult } from '@/types/chat'
import ChatBreadcrumbs from './ChatBreadcrumbs.vue'
import VoiceBrandBar from './VoiceBrandBar.vue'
import ChatCard from './ChatCard.vue'
import RadarScanCanvas from './RadarScanCanvas.vue'
import FathometerGauge from '@/components/FathometerGauge.vue'
import MiniSpeedLossChart from './MiniSpeedLossChart.vue'
import MiniWaterfallChart from './MiniWaterfallChart.vue'
import VesselRankingCard from './VesselRankingCard.vue'
import VesselCompareCard from './VesselCompareCard.vue'
import MaintenanceRecommendationCard from '@/components/MaintenanceRecommendationCard.vue'

const chatContext = useChatContextStore()
const router = useRouter()
const voice = useChatVoiceInput(handleSubmit)

watch(
  () => chatContext.open,
  (isOpen) => {
    if (isOpen) voice.enterListening()
    else voice.stop()
  },
)

function resetConversation() {
  voice.stop()
  chatContext.reset()
  voice.enterListening()
}

const SUGGESTED_QUESTIONS = [
  'YM WELLNESS 現在狀況怎麼樣？',
  '哪些船需要優先安排維修？',
  '比較 YM WELLNESS 跟 YM VICTORY 的污損趨勢',
  '上次水下清洗是什麼時候？',
]

const loading = ref(false)
const revealedCount = ref(0)
let revealTimers: ReturnType<typeof setTimeout>[] = []

function clearRevealTimers() {
  revealTimers.forEach((t) => clearTimeout(t))
  revealTimers = []
}

function reduceMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

watch(
  () => chatContext.activeTurn,
  (turn) => {
    clearRevealTimers()
    if (!turn || !turn.cards.length) {
      revealedCount.value = 0
      return
    }
    if (reduceMotion()) {
      revealedCount.value = turn.cards.length
      return
    }
    revealedCount.value = 0
    turn.cards.forEach((_, i) => {
      revealTimers.push(setTimeout(() => (revealedCount.value = i + 1), (i + 1) * 200))
    })
  },
  { immediate: true },
)

function viewFullPage(path: string) {
  chatContext.closeChat()
  router.push(path)
}

function makeErrorTurn(userText: string, message: string): ChatTurn {
  return {
    id: `turn-error-${Date.now()}`,
    userText,
    intent: 'out_of_scope',
    replyText: `發生錯誤：${message}`,
    cards: [],
    vesselImo: null,
    vesselName: null,
    breadcrumbLabel: '錯誤',
  }
}

async function handleSubmit(text: string) {
  loading.value = true
  try {
    const body: NluRequestBody = { message: text, history: chatContext.history }
    const res = await fetch('/api/nlu', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      throw new Error(err?.error ?? 'NLU 請求失敗')
    }
    const nlu = (await res.json()) as NluResult
    const turn = await resolveChatTurn(text, nlu, chatContext.activeTurn)
    chatContext.pushTurn(turn)
  } catch (err) {
    chatContext.pushTurn(makeErrorTurn(text, err instanceof Error ? err.message : '未知錯誤'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <Transition name="voicebot-fade">
    <div v-if="chatContext.open" class="fixed inset-0 z-50 flex flex-col" role="dialog" aria-modal="true" aria-label="對話模式">
      <div class="absolute inset-0 voicebot-scrim" @click="chatContext.closeChat()" />
      <RadarScanCanvas class="opacity-60" />

      <div class="relative z-10 flex flex-col h-full max-w-[900px] w-full mx-auto px-4 py-6 gap-4">
        <div class="flex items-center justify-between gap-3">
          <ChatBreadcrumbs />
          <div class="flex items-center gap-2 shrink-0">
            <button
              v-if="chatContext.turns.length"
              type="button"
              class="text-xs font-display uppercase tracking-wide px-3 py-1.5 rounded-[2px] border border-[var(--color-on-navy)]/35 text-[var(--color-on-navy)] hover:bg-[var(--color-on-navy)]/10 transition-colors flex items-center gap-1.5"
              title="清除紀錄，重新開始"
              @click="resetConversation"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M4 4v6h6M20 20v-6h-6M4.5 15a8 8 0 0 0 14.3 3M19.5 9A8 8 0 0 0 5.2 6"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              重新開始
            </button>
            <button
              type="button"
              class="text-xs font-display uppercase tracking-wide px-3 py-1.5 rounded-[2px] border border-[var(--color-on-navy)]/35 text-[var(--color-on-navy)] hover:bg-[var(--color-on-navy)]/10 transition-colors"
              @click="chatContext.closeChat()"
            >
              返回儀表板（ESC）
            </button>
          </div>
        </div>

        <div class="flex-1 min-h-0 overflow-y-auto flex flex-col gap-4 pr-1">
          <div v-if="!chatContext.turns.length" class="flex-1 min-h-[240px] flex flex-col items-center justify-center text-center gap-5">
            <div class="flex flex-col gap-2">
              <h1 class="font-display text-2xl md:text-3xl text-[var(--color-on-navy)]">
                您好！我是 AI 語音助理
              </h1>
              <p class="text-[var(--color-on-navy)]/75 text-sm max-w-sm mx-auto">
                請問您想了解船舶什麼資訊？試著問問看，或直接開口說話：
              </p>
            </div>
            <div class="flex flex-wrap justify-center gap-2 max-w-lg">
              <button
                v-for="q in SUGGESTED_QUESTIONS"
                :key="q"
                type="button"
                class="text-xs font-body px-3 py-1.5 rounded-full border border-[var(--color-fathom-teal-glow)]/40 text-[var(--color-on-navy)]/85 hover:border-[var(--color-fathom-teal-glow)] hover:bg-[var(--color-fathom-teal-glow)]/10 transition-colors"
                @click="handleSubmit(q)"
              >
                {{ q }}
              </button>
            </div>
          </div>

          <template v-else-if="chatContext.activeTurn">
            <p class="font-display text-base text-[var(--color-on-navy)] whitespace-pre-line">
              {{ chatContext.activeTurn.replyText }}
            </p>

            <button
              v-if="chatContext.activeTurn.vesselImo"
              type="button"
              class="self-start flex items-center gap-1.5 text-xs font-data text-[var(--color-fathom-teal-glow)] hover:text-white transition-colors"
              @click="viewFullPage(`/vessels/${chatContext.activeTurn.vesselImo}/overview`)"
            >
              <span class="underline">點擊此處前往查看船舶詳情</span>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>

            <TransitionGroup name="chat-card-fade" tag="div" class="flex flex-col gap-3">
              <template v-for="(card, i) in chatContext.activeTurn.cards.slice(0, revealedCount)" :key="card.type + i">
                <ChatCard
                  v-if="card.type === 'gauge'"
                  code="CHAT-G1"
                  title="船體污損 / Speed Loss"
                  :to="`/vessels/${card.vessel.imo}/overview`"
                >
                  <FathometerGauge
                    :value="Math.min(100, card.vessel.speedLossPct * 8)"
                    :grade="card.vessel.foulingGrade"
                    label="目前 SPEED LOSS"
                    :display-value="`${card.vessel.speedLossPct.toFixed(1)}%`"
                  />
                </ChatCard>

                <ChatCard
                  v-else-if="card.type === 'speedLoss'"
                  code="CHAT-S1"
                  title="Speed Loss 趨勢"
                  :to="`/vessels/${card.vessel.imo}/speed-loss`"
                >
                  <MiniSpeedLossChart :series="card.series" />
                </ChatCard>

                <div v-else-if="card.type === 'maintenance'" class="flex flex-col gap-1">
                  <MaintenanceRecommendationCard :data="card.data" />
                  <div class="flex justify-end">
                    <button
                      type="button"
                      class="text-[10px] font-display uppercase tracking-wide px-2 py-1 rounded-[2px] border border-[var(--color-fathom-teal)]/50 text-[var(--color-fathom-teal)] hover:bg-[var(--color-fathom-teal)]/10 transition-colors"
                      @click="viewFullPage(`/vessels/${card.vessel.imo}/maintenance-correlation`)"
                    >
                      查看完整頁面
                    </button>
                  </div>
                </div>

                <ChatCard
                  v-else-if="card.type === 'fuelWaterfall'"
                  code="CHAT-F1"
                  title="油耗歸因（精簡版）"
                  :to="`/vessels/${card.vessel.imo}/fuel-attribution`"
                >
                  <MiniWaterfallChart :data="card.data" />
                </ChatCard>

                <ChatCard v-else-if="card.type === 'ranking'" code="CHAT-R1" title="優先維修排行" to="/vessels">
                  <VesselRankingCard :vessels="card.vessels" />
                </ChatCard>

                <ChatCard v-else-if="card.type === 'compare'" code="CHAT-C1" title="污損趨勢比較" to="/fleet-analytics">
                  <VesselCompareCard :a="card.a" :b="card.b" />
                </ChatCard>
              </template>
            </TransitionGroup>
          </template>

          <p v-if="loading" class="font-data text-xs text-[var(--color-on-navy)]/60">理解中…</p>
        </div>

        <!-- One unified brand-red instrument bar (logo + waveform + controls)
             at the very bottom, away from the radar canvas's center-focused
             rings/sweep so the two visuals don't compete for space. -->
        <VoiceBrandBar :voice="voice" />
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* Solid, thick brand-color scrim — deliberately opaque (no dashboard bleeding
   through) so entering VoiceBot mode reads as switching the operating
   surface, not opening a translucent panel over the same screen. */
.voicebot-scrim {
  background:
    radial-gradient(140% 90% at 50% -10%, var(--color-marine-navy-light) 0%, var(--color-marine-navy-deep) 60%),
    var(--color-marine-navy-deep);
}

.voicebot-fade-enter-from,
.voicebot-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: no-preference) {
  .voicebot-fade-enter-active,
  .voicebot-fade-leave-active {
    transition: opacity var(--motion-glide) var(--ease-instrument);
  }
}

.chat-card-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

@media (prefers-reduced-motion: no-preference) {
  .chat-card-fade-enter-active {
    transition: opacity 200ms var(--ease-instrument), transform 200ms var(--ease-instrument);
  }
}
</style>
