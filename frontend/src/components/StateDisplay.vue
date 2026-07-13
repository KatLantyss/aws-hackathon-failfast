<script setup lang="ts">
withDefaults(
  defineProps<{
    state: 'loading' | 'empty' | 'error'
    emptyTitle?: string
    emptyHint?: string
    errorMessage?: string | null
  }>(),
  {
    emptyTitle: '尚無資料',
    emptyHint: '',
    errorMessage: null,
  },
)
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-3 py-16 text-center">
    <template v-if="state === 'loading'">
      <div class="relative h-10 w-24" aria-hidden="true">
        <div class="absolute inset-y-0 left-0 w-1/3 bg-[var(--color-brass-amber)]/70 animate-[sweep_1.2s_ease-in-out_infinite]" />
      </div>
      <p class="font-data text-xs uppercase tracking-wide text-[var(--color-ink-slate)]/60">讀取數據中…</p>
    </template>

    <template v-else-if="state === 'empty'">
      <svg class="h-8 w-8 text-[var(--color-ink-slate)]/40" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M3 12h18M3 6h18M3 18h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
      </svg>
      <p class="font-display text-sm text-[var(--color-ink-slate)]">{{ emptyTitle }}</p>
      <p v-if="emptyHint" class="text-sm text-[var(--color-ink-slate)]/70 max-w-sm">{{ emptyHint }}</p>
    </template>

    <template v-else>
      <svg class="h-8 w-8 text-[var(--color-signal-red)]" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a1 1 0 0 0 .87 1.5h18.62a1 1 0 0 0 .87-1.5L13.71 3.86a1 1 0 0 0-1.72 0Z"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linejoin="round"
        />
      </svg>
      <p class="font-display text-sm text-[var(--color-signal-red)]">讀取失敗</p>
      <p class="text-sm text-[var(--color-ink-slate)]/70 max-w-sm">{{ errorMessage ?? '請稍後重試，或聯絡系統管理員。' }}</p>
    </template>
  </div>
</template>

<style scoped>
@keyframes sweep {
  0% {
    left: -33%;
  }
  100% {
    left: 100%;
  }
}
</style>
