<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import { useRouter } from 'vue-router'
import PanelTag from '@/components/PanelTag.vue'
import { useChatContextStore } from '@/stores/chatContext'

const props = defineProps<{ code: string; title: string; to?: RouteLocationRaw }>()

const router = useRouter()
const chatContext = useChatContextStore()

function goToFullPage() {
  if (!props.to) return
  chatContext.closeChat()
  router.push(props.to)
}
</script>

<template>
  <div class="panel p-3 flex flex-col gap-2">
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <PanelTag :code="code" />
        <span class="font-display text-xs tracking-wide text-[var(--color-ink-slate)]/70">{{ title }}</span>
      </div>
      <button
        v-if="to"
        type="button"
        class="text-[10px] font-display uppercase tracking-wide px-2 py-1 rounded-[2px] border border-[var(--color-fathom-teal)]/50 text-[var(--color-fathom-teal)] hover:bg-[var(--color-fathom-teal)]/10 transition-colors"
        @click="goToFullPage"
      >
        查看完整頁面
      </button>
    </div>
    <slot />
  </div>
</template>
