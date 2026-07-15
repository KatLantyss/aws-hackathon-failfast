<script setup lang="ts">
// ALT-01 預警門檻設定 — 純前端 stub 示意元件，尚未串接後端 API 或寄信服務。
// 由 VesselLayout.vue（頁籤外層）持有實際的滑桿/名單狀態並以 v-model 傳入，
// 讓設定值在關閉視窗、切換頁籤後仍保留；本元件只負責彈窗呈現與「確認」互動。
import { ref, watch } from 'vue'
import type { VesselSummary } from '@/types/fleet'
import type { DataSourceInfo } from '@/types/dataSource'
import DataSourceTag from '@/components/DataSourceTag.vue'

defineProps<{
  vessel: VesselSummary
}>()

const open = defineModel<boolean>('open', { default: false })
const thresholdPct = defineModel<number>('thresholdPct', { default: 8 })
const daysBefore = defineModel<number>('daysBefore', { default: 14 })
const enabled = defineModel<boolean>('enabled', { default: true })
const notifyEmails = defineModel<string>('notifyEmails', { default: '' })

const justConfirmed = ref(false)

watch(open, (isOpen) => {
  if (isOpen) justConfirmed.value = false
})

const dsAlert: DataSourceInfo = {
  status: 'stub',
  description: '滑桿、啟用開關與通知 email 名單都是純前端 UI 狀態（ref），「確認」只會顯示完成提示，不會呼叫任何 API 或真的寄信 —— 重新整理頁面就重置，是互動式模擬器而非持久化設定。',
  fields: [
    { ui: 'Speed Loss 門檻 / 提前天數滑桿', source: '純前端 ref，無對應後端欄位' },
    { ui: '通知 email 名單', source: '純前端字串，預設 {船名}@yangming.com.tw，未串接任何寄信服務' },
  ],
}

function close() {
  open.value = false
}
function confirm() {
  justConfirmed.value = true
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/50" @click="close" />
      <div
        class="relative panel p-5 w-full max-w-lg max-h-[85vh] overflow-y-auto flex flex-col gap-4"
        role="dialog"
        aria-modal="true"
        aria-label="設定 Speed Loss 告警"
      >
        <DataSourceTag :info="dsAlert" />
        <div class="flex items-center justify-between pr-8">
          <p class="font-display text-sm">⚡ 設定 Speed Loss 告警 — {{ vessel.name }}</p>
          <button type="button" class="text-[var(--color-ink-slate)]/50 hover:text-[var(--color-ink-slate)] text-lg leading-none" @click="close">
            ✕
          </button>
        </div>

        <template v-if="!justConfirmed">
          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input v-model="enabled" type="checkbox" class="accent-[var(--color-brass-amber)] w-4 h-4" />
            啟用預警
          </label>

          <div>
            <label class="text-xs text-[var(--color-ink-slate)]/60 block mb-1">Speed Loss 門檻 (%)</label>
            <input
              v-model.number="thresholdPct"
              type="range"
              min="3"
              max="15"
              step="0.5"
              class="w-full accent-[var(--color-brass-amber)]"
            />
            <div class="flex justify-between text-xs font-data text-[var(--color-ink-slate)]/60 mt-1">
              <span>3%</span>
              <span class="font-bold text-[var(--color-ink-slate)]">{{ thresholdPct }}%</span>
              <span>15%</span>
            </div>
          </div>

          <div>
            <label class="text-xs text-[var(--color-ink-slate)]/60 block mb-1">提前幾天警報</label>
            <input
              v-model.number="daysBefore"
              type="range"
              min="3"
              max="60"
              step="1"
              class="w-full accent-[var(--color-brass-amber)]"
            />
            <div class="flex justify-between text-xs font-data text-[var(--color-ink-slate)]/60 mt-1">
              <span>3天</span>
              <span class="font-bold text-[var(--color-ink-slate)]">{{ daysBefore }} 天</span>
              <span>60天</span>
            </div>
          </div>

          <label class="flex flex-col gap-1 text-sm">
            <span class="text-xs text-[var(--color-ink-slate)]/60">通知 email 名單（多筆請用逗號分隔）</span>
            <input v-model="notifyEmails" type="text" class="field font-data text-sm" placeholder="example@yangming.com.tw" />
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
              class="border rounded-[2px] px-3 py-1.5 text-xs font-display uppercase tracking-wide bg-[var(--color-brass-amber)] text-white border-[var(--color-brass-amber)] hover:opacity-90 transition-opacity"
              @click="confirm"
            >
              確認
            </button>
          </div>
        </template>

        <template v-else>
          <div class="flex flex-col items-center gap-2 py-4 text-center">
            <span class="status-dot bg-[var(--color-fathom-teal)]" />
            <p class="font-display text-sm">已完成設定</p>
            <p class="text-xs text-[var(--color-ink-slate)]/60 max-w-xs">
              Speed Loss 預警門檻與通知名單已更新（僅前端示意，尚未串接後端 API 或寄信服務）。
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
