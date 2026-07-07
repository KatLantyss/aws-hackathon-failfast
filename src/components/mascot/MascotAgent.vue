<script setup lang="ts">
import { ref, reactive, nextTick } from 'vue'
import { useMascotBrain } from '@/composables/useMascotBrain'

interface ChatMessage {
  role: 'mascot' | 'user'
  text: string
}

const { ask } = useMascotBrain()

const open = ref(false)
const input = ref('')
const thinking = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const messages = reactive<ChatMessage[]>([
  { role: 'mascot', text: '嗨！我是 YM 節能小幫手 🐬 想看船隊狀況、儀表板還是歷史紀錄？直接問我就可以！' }
])

const pos = reactive({ x: 24, y: 24 })
let dragging = false
let dragMoved = false
let startX = 0
let startY = 0

function onPointerDown(e: PointerEvent) {
  dragging = true
  dragMoved = false
  startX = e.clientX
  startY = e.clientY
  ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  if (!dragging) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragMoved = true
  startX = e.clientX
  startY = e.clientY
  pos.x = Math.min(Math.max(8, pos.x - dx), window.innerWidth - 72)
  pos.y = Math.min(Math.max(8, pos.y - dy), window.innerHeight - 72)
}

function onPointerUp() {
  dragging = false
}

function toggleOpen() {
  if (dragMoved) return
  open.value = !open.value
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

async function send() {
  const text = input.value.trim()
  if (!text || thinking.value) return
  messages.push({ role: 'user', text })
  input.value = ''
  thinking.value = true
  scrollToBottom()

  const reply = await ask(text)
  thinking.value = false
  messages.push({ role: 'mascot', text: reply.text })
  scrollToBottom()
}
</script>

<template>
  <div class="mascot-root" :style="{ right: pos.x + 'px', bottom: pos.y + 'px' }">
    <v-expand-transition>
      <v-sheet v-if="open" rounded="lg" color="card" class="mascot-panel" elevation="12">
        <div class="d-flex align-center justify-space-between px-3 py-2 mascot-header">
          <div class="d-flex align-center ga-2">
            <span class="mascot-emoji">🐬</span>
            <span class="text-subtitle-2 font-weight-medium">YM 節能小幫手</span>
          </div>
          <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
        </div>

        <div ref="messagesEl" class="mascot-messages px-3 py-2">
          <div v-for="(m, i) in messages" :key="i" class="d-flex mb-2" :class="m.role === 'user' ? 'justify-end' : 'justify-start'">
            <div class="mascot-bubble" :class="m.role">{{ m.text }}</div>
          </div>
          <div v-if="thinking" class="d-flex justify-start mb-2">
            <div class="mascot-bubble mascot typing-bubble">
              <span class="typing-dot" /><span class="typing-dot" /><span class="typing-dot" />
            </div>
          </div>
        </div>

        <div class="d-flex align-center px-2 py-2 ga-2 mascot-input">
          <v-text-field
            v-model="input"
            density="compact"
            variant="solo"
            hide-details
            placeholder="問我：哪艘船風險最高？"
            @keydown.enter="send"
          />
          <v-btn icon="mdi-send" color="primary" size="small" @click="send" />
        </div>
      </v-sheet>
    </v-expand-transition>

    <button
      class="mascot-fab"
      :class="{ 'mascot-fab--idle': !open }"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @click="toggleOpen"
    >
      <span v-if="!open" class="mascot-fab-ring" />
      🐬
    </button>
  </div>
</template>

<style scoped>
.mascot-root {
  position: fixed;
  z-index: 2500;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
}

.mascot-fab {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #00c2ff, #00e0a0);
  border: none;
  font-size: 28px;
  cursor: grab;
  box-shadow: 0 6px 18px rgba(0, 194, 255, 0.35);
  touch-action: none;
}

.mascot-fab:active {
  cursor: grabbing;
}

.mascot-fab--idle {
  animation: mascot-bob 2.4s ease-in-out infinite;
}

.mascot-fab-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid rgba(0, 224, 160, 0.6);
  animation: mascot-ring 2.4s ease-out infinite;
  pointer-events: none;
}

@keyframes mascot-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

@keyframes mascot-ring {
  0% { transform: scale(1); opacity: 0.7; }
  100% { transform: scale(1.6); opacity: 0; }
}

.mascot-panel {
  width: 320px;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.mascot-header {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.mascot-emoji {
  font-size: 20px;
}

.mascot-messages {
  height: 280px;
  overflow-y: auto;
}

.mascot-bubble {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.4;
}

.mascot-bubble.mascot {
  background: rgba(0, 194, 255, 0.12);
  color: #e6f6ff;
}

.mascot-bubble.user {
  background: rgba(255, 255, 255, 0.1);
}

.typing-bubble {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 14px;
}

.typing-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #00c2ff;
  animation: typing-bounce 1.2s ease-in-out infinite;
}

.typing-dot:nth-child(2) {
  animation-delay: 0.15s;
}

.typing-dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-4px); opacity: 1; }
}

.mascot-input {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
</style>
