<script setup lang="ts">
import { useChatContextStore } from '@/stores/chatContext'

const chatContext = useChatContextStore()
</script>

<template>
  <nav v-if="chatContext.turns.length" class="flex items-center gap-1.5 overflow-x-auto text-xs font-data whitespace-nowrap">
    <template v-for="(turn, i) in chatContext.turns" :key="turn.id">
      <button
        type="button"
        class="px-1.5 py-0.5 rounded-[2px] transition-colors"
        :class="i === chatContext.activeTurnIndex ? 'text-[var(--color-fathom-teal-glow)] border border-[var(--color-fathom-teal-glow)]/50' : 'text-[var(--color-on-navy)]/55 hover:text-[var(--color-fathom-teal-glow)]'"
        @click="chatContext.goToTurn(i)"
      >
        {{ turn.breadcrumbLabel }}
      </button>
      <span v-if="i < chatContext.turns.length - 1" class="text-[var(--color-on-navy)]/30">›</span>
    </template>
  </nav>
</template>
