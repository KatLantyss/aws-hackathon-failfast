<script setup lang="ts">
// 提交養護工單申請 — 示意呈現用元件，尚未串接後端 API。送出後只更新本地
// 呼叫端的狀態（見 v-model:open + submitted 事件），重新整理頁面即重置。
import { ref, watch } from 'vue'
import type { VesselSummary } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import DataSourceTag from '@/components/DataSourceTag.vue'

const props = defineProps<{ vessel: VesselSummary; defaultNote?: string }>()
const emit = defineEmits<{ submitted: [note: string] }>()
const open = defineModel<boolean>('open', { default: false })

const note = ref('')
const submitting = ref(false)
const justSubmitted = ref(false)

watch(open, (isOpen) => {
  if (isOpen) {
    note.value = props.defaultNote ?? ''
    submitting.value = false
    justSubmitted.value = false
  }
})

const dsInfo: DataSourceInfo = {
  status: 'stub',
  description: '示意呈現：送出後僅更新前端狀態（本頁的養護狀態徽章），未呼叫任何後端 API，重新整理頁面即會重置為原始狀態。',
}

function close() {
  open.value = false
}

async function submit() {
  submitting.value = true
  await new Promise((resolve) => setTimeout(resolve, 500))
  submitting.value = false
  justSubmitted.value = true
  emit('submitted', note.value)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/50" @click="close" />
      <div class="relative panel p-5 w-full max-w-md flex flex-col gap-4" role="dialog" aria-modal="true" aria-label="申請養護">
        <DataSourceTag :info="dsInfo" />
        <div class="flex items-center justify-between">
          <p class="font-display text-sm tracking-wide">申請養護 — {{ vessel.name }}</p>
          <button type="button" class="text-[var(--color-ink-slate)]/50 hover:text-[var(--color-ink-slate)] text-lg leading-none" @click="close">
            ✕
          </button>
        </div>

        <template v-if="!justSubmitted">
          <label class="flex flex-col gap-1 text-sm">
            <span class="text-xs text-[var(--color-ink-slate)]/60">申請原因／備註（選填）</span>
            <textarea
              v-model="note"
              rows="4"
              class="field font-body text-sm"
              placeholder="例如：本日 Speed Loss 已超過門檻，建議安排船殼清洗…"
            />
          </label>
          <div class="flex justify-end gap-2">
            <button
              type="button"
              class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
              @click="close"
            >
              取消
            </button>
            <button
              type="button"
              class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide bg-[var(--color-brass-amber)] text-white border-[var(--color-brass-amber)] hover:opacity-90 transition-opacity disabled:opacity-40"
              :disabled="submitting"
              @click="submit"
            >
              {{ submitting ? '送出中…' : '送出申請' }}
            </button>
          </div>
        </template>

        <template v-else>
          <div class="flex flex-col items-center gap-2 py-4 text-center">
            <span class="status-dot bg-[var(--color-fathom-teal)]" />
            <p class="font-display text-sm">已送出養護申請</p>
            <p class="text-xs text-[var(--color-ink-slate)]/60 max-w-xs">
              狀態已更新為「已申請養護」（僅前端示意，尚未串接後端 API）。
            </p>
          </div>
          <div class="flex justify-end">
            <button
              type="button"
              class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide hover:border-[var(--color-brass-amber)] hover:text-[var(--color-brass-amber)] transition-colors"
              @click="close"
            >
              關閉
            </button>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>
