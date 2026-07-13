<script setup lang="ts">
import type { ChatVoiceInput } from '@/composables/useChatVoiceInput'

defineProps<{ voice: ChatVoiceInput }>()
</script>

<template>
  <div class="flex flex-col gap-2">
    <div class="panel flex items-center gap-3 p-2 pl-3">
      <template v-if="voice.mode.value === 'listening'">
        <span
          class="flex-1 font-data text-xs tracking-wide truncate"
          :class="voice.notice.value?.kind === 'failed' ? 'text-[var(--color-signal-red)]' : 'text-[var(--color-fathom-teal)]'"
        >
          {{ voice.statusLabel.value }}
        </span>
        <button
          type="button"
          class="h-9 px-3 shrink-0 rounded-[2px] font-display text-xs uppercase tracking-wide border border-[var(--color-fathom-teal)] text-[var(--color-fathom-teal)] hover:bg-[var(--color-fathom-teal)]/10 transition-colors disabled:opacity-40 flex items-center gap-1.5"
          :disabled="voice.recorder.status.value === 'transcribing'"
          @click="voice.finishSpeaking()"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M21 3 3 10.5l7.5 2.5M21 3l-7.5 18-2.5-7.5M21 3 10.5 13"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          送出
        </button>
      </template>

      <template v-else>
        <input
          v-model="voice.inputText.value"
          type="text"
          :placeholder="voice.mode.value === 'reviewing' ? '確認或修改語音辨識結果…' : '輸入問題，例如：YM WELLNESS 現在狀況怎麼樣？'"
          class="flex-1 bg-transparent outline-none text-sm font-body"
          autofocus
          @keydown.enter="voice.confirmSend()"
        />
        <button
          v-if="voice.mode.value === 'reviewing'"
          type="button"
          class="h-9 px-3 shrink-0 rounded-[2px] font-display text-xs uppercase tracking-wide border border-[var(--color-ink-slate)]/30 hover:border-[var(--color-signal-red)] hover:text-[var(--color-signal-red)] transition-colors"
          @click="voice.cancelReview()"
        >
          重新錄音
        </button>
        <button
          type="button"
          class="h-9 px-3 shrink-0 rounded-[2px] font-display text-xs uppercase tracking-wide border border-[var(--color-brass-amber)] text-[var(--color-brass-amber)] hover:bg-[var(--color-brass-amber)]/10 transition-colors disabled:opacity-40"
          :disabled="!voice.inputText.value.trim()"
          @click="voice.confirmSend()"
        >
          送出
        </button>
      </template>

      <button
        v-if="voice.mode.value !== 'reviewing'"
        type="button"
        class="relative h-9 w-9 shrink-0 rounded-full flex items-center justify-center border transition-colors"
        :class="
          voice.mode.value === 'listening'
            ? 'border-[var(--color-fathom-teal)] text-[var(--color-fathom-teal)]'
            : 'border-[var(--color-ink-slate)]/30 hover:border-[var(--color-fathom-teal)] hover:text-[var(--color-fathom-teal)]'
        "
        :aria-label="voice.mode.value === 'listening' ? '暫停語音聆聽' : '開始語音聆聽'"
        :title="voice.mode.value === 'listening' ? '暫停語音聆聽' : '開始語音聆聽'"
        @click="voice.mode.value === 'listening' ? voice.enterTyping() : voice.enterListening()"
      >
        <svg viewBox="0 0 24 24" fill="none" class="h-4 w-4 relative z-10">
          <circle cx="12" cy="3.2" r="1.1" fill="currentColor" />
          <path d="M12 4.3v2.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          <rect x="5" y="6.5" width="14" height="12" rx="3" stroke="currentColor" stroke-width="1.6" />
          <circle cx="9.3" cy="12" r="1.15" fill="currentColor" />
          <circle cx="14.7" cy="12" r="1.15" fill="currentColor" />
          <path d="M9 15.3h6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
          <path d="M5 10.5H3M21 10.5h-2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
        </svg>
      </button>
    </div>

    <button
      v-if="voice.mode.value !== 'reviewing'"
      type="button"
      class="self-end text-[11px] font-data text-[var(--color-on-navy)]/45 hover:text-[var(--color-on-navy)]/80 transition-colors"
      @click="voice.mode.value === 'listening' ? voice.enterTyping() : voice.enterListening()"
    >
      {{ voice.mode.value === 'listening' ? '改用文字輸入' : '改用語音聆聽' }}
    </button>
  </div>
</template>
