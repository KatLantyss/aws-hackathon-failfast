<script setup lang="ts">
// Unified instrument bar: logo + the voice-reactive waveform + input
// controls all live in one block, instead of stacking separate pieces.
import type { ChatVoiceInput } from '@/composables/useChatVoiceInput'
import yangMingLogo from '@/assets/yangming_logo.png'
import SiriWaveform from './SiriWaveform.vue'

defineProps<{ voice: ChatVoiceInput }>()
</script>

<template>
  <div class="voice-brand-bar rounded-[4px] flex flex-col gap-2 px-3 pb-3 pt-3">
    <div class="flex items-center gap-3">
      <span
        class="grid place-items-center h-11 w-11 rounded-[3px] border border-[var(--color-brand-red)]/60 bg-white/[0.06] shrink-0 overflow-hidden"
      >
        <img :src="yangMingLogo" alt="陽明海運" class="h-7 w-7 object-contain" />
      </span>
      <SiriWaveform
        class="flex-1 h-16"
        :analyser="voice.recorder.analyser.value"
        :active="voice.mode.value === 'listening' && !voice.thinking.value"
      />
    </div>

    <div class="flex items-center gap-3">
      <template v-if="voice.mode.value === 'listening'">
        <span
          class="flex-1 font-data text-xs tracking-wide truncate flex items-center gap-1.5"
          :class="voice.notice.value?.kind === 'failed' ? 'text-white' : 'text-white/85'"
        >
          <span v-if="voice.notice.value?.kind === 'failed'" aria-hidden="true">⚠</span>
          {{ voice.statusLabel.value }}
        </span>
        <button
          type="button"
          class="voice-send-btn h-9 px-4 shrink-0 flex items-center gap-1.5 disabled:opacity-40"
          :disabled="voice.recorder.status.value === 'transcribing' || voice.thinking.value"
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
          class="voice-text-input flex-1"
          autofocus
          @keydown.enter="voice.confirmSend()"
        />
        <button
          v-if="voice.mode.value === 'reviewing'"
          type="button"
          class="h-8 px-2 shrink-0 rounded-[2px] font-data text-[11px] text-white/45 hover:text-white/80 transition-colors flex items-center gap-1"
          title="重新錄音"
          @click="voice.cancelReview()"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M4 4v6h6M20 20v-6h-6M4.5 15a8 8 0 0 0 14.3 3M19.5 9A8 8 0 0 0 5.2 6"
              stroke="currentColor"
              stroke-width="1.7"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          重新錄音
        </button>
        <button
          type="button"
          class="voice-send-btn h-9 px-4 shrink-0 flex items-center gap-1.5 disabled:opacity-40"
          :class="{ 'ml-1': voice.mode.value === 'reviewing' }"
          :disabled="!voice.inputText.value.trim()"
          @click="voice.confirmSend()"
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

      <button
        v-if="voice.mode.value !== 'reviewing'"
        type="button"
        class="relative h-9 w-9 shrink-0 rounded-full flex items-center justify-center border transition-colors disabled:opacity-40"
        :class="voice.mode.value === 'listening' ? 'border-white text-white' : 'border-white/50 text-white/70 hover:border-white hover:text-white'"
        :disabled="voice.thinking.value"
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
      class="self-end text-[11px] font-data text-white/55 hover:text-white/90 transition-colors"
      @click="voice.mode.value === 'listening' ? voice.enterTyping() : voice.enterListening()"
    >
      {{ voice.mode.value === 'listening' ? '改用文字輸入' : '改用語音聆聽' }}
    </button>
  </div>
</template>

<style scoped>
/* Dark "instrument panel" gradient with a glowing teal edge — matches the
   radar/waveform's own sonar palette instead of a flat brand-color fill, so
   it reads as a piece of tech hardware rather than a marketing banner. */
.voice-brand-bar {
  background: linear-gradient(180deg, var(--color-marine-navy-light) 0%, var(--color-marine-navy) 55%, var(--color-marine-navy-deep) 100%);
  border: 1px solid color-mix(in srgb, var(--color-fathom-teal-glow) 35%, transparent);
  box-shadow:
    0 0 28px color-mix(in srgb, var(--color-fathom-teal-glow) 16%, transparent),
    var(--elevation-3);
}

/* The primary action in this bar — solid fill + glow, deliberately much
   heavier than the ghost/ text-only secondary actions next to it (e.g.
   重新錄音) so the two are never mistaken for equally-weighted choices. */
.voice-send-btn {
  border-radius: var(--radius-chart);
  font-family: var(--font-display);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-marine-navy-deep);
  background: linear-gradient(180deg, var(--color-fathom-teal-glow) 0%, var(--color-fathom-teal) 100%);
  box-shadow: 0 2px 10px color-mix(in srgb, var(--color-fathom-teal-glow) 45%, transparent);
  transition: filter 150ms ease, transform 150ms ease;
}
.voice-send-btn:hover:not(:disabled) {
  filter: brightness(1.08);
  transform: translateY(-1px);
}
.voice-send-btn:active:not(:disabled) {
  transform: translateY(0);
}

.voice-text-input {
  height: 42px;
  border-radius: 5px;
  padding: 0 14px;
  background: var(--color-chart-paper-hi);
  border: 1px solid color-mix(in srgb, var(--color-fathom-teal) 30%, transparent);
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.12);
  outline: none;
  font-family: var(--font-body);
  font-size: 15px;
  letter-spacing: 0.01em;
  color: var(--color-ink-slate);
  transition: border-color 150ms ease, box-shadow 150ms ease;
}
.voice-text-input::placeholder {
  color: var(--color-ink-muted);
  font-style: italic;
}
.voice-text-input:focus {
  border-color: var(--color-fathom-teal);
  box-shadow:
    inset 0 1px 3px rgba(0, 0, 0, 0.12),
    0 0 0 3px color-mix(in srgb, var(--color-fathom-teal-glow) 30%, transparent);
}
</style>
