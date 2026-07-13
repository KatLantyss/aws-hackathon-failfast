<script setup lang="ts">
// No background block on purpose — the credit line should read as a quiet
// instrument-panel etching on the page itself, not a bolted-on bar.
</script>

<template>
  <footer class="relative z-10 mt-auto py-8 flex flex-col items-center gap-2 text-center">
    <div
      class="flex items-center gap-3 font-mono text-[10px] tracking-[0.24em] uppercase text-[var(--color-ink-muted)]"
    >
      <span class="h-px w-8 bg-current opacity-25" aria-hidden="true" />
      <span>Web Design by eCV FailFast Team</span>
      <span class="h-px w-8 bg-current opacity-25" aria-hidden="true" />
    </div>
    <p class="font-mono text-[10px] tracking-[0.03em] text-[var(--color-ink-muted)]/70">
      © 2026 eCloudvalley Digital Technology Co., Ltd. or its affiliates. All rights reserved.
    </p>
  </footer>
</template>
