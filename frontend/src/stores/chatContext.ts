import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { ChatHistoryMessage, ChatSessionMemory, ChatTurn } from '@/types/chat'

export const useChatContextStore = defineStore('chatContext', () => {
  const open = ref(false)
  const turns = ref<ChatTurn[]>([])
  const activeTurnIndex = ref(-1)

  const activeTurn = computed<ChatTurn | null>(() =>
    activeTurnIndex.value >= 0 ? turns.value[activeTurnIndex.value] ?? null : null,
  )

  const history = computed<ChatHistoryMessage[]>(() =>
    turns.value.slice(-3).flatMap((turn) => [
      { role: 'user' as const, content: turn.userText },
      { role: 'assistant' as const, content: turn.replyText },
    ]),
  )

  const sessionMemory = computed<ChatSessionMemory>(() => {
    const pendingTurn = [...turns.value].reverse().find((turn) => turn.awaitingVesselFor)
    const pending = pendingTurn?.awaitingVesselFor
    return {
      pendingEntityResolution: pendingTurn && pending
        ? {
            userText: pendingTurn.userText,
            assistantReply: pendingTurn.replyText,
            intent: pending.intent,
            factType: pending.factType,
            suggestedVesselImo: pending.suggestedVesselImo ?? null,
          }
        : null,
    }
  })

  function openChat() {
    open.value = true
  }

  function closeChat() {
    open.value = false
  }

  function toggleChat() {
    open.value = !open.value
  }

  function pushTurn(turn: ChatTurn) {
    turns.value.push(turn)
    activeTurnIndex.value = turns.value.length - 1
  }

  function goToTurn(index: number) {
    if (index >= 0 && index < turns.value.length) {
      activeTurnIndex.value = index
    }
  }

  function reset() {
    turns.value = []
    activeTurnIndex.value = -1
  }

  return { open, turns, activeTurnIndex, activeTurn, history, sessionMemory, openChat, closeChat, toggleChat, pushTurn, goToTurn, reset }
})
