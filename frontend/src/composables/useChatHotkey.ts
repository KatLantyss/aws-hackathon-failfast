import { onMounted, onUnmounted } from 'vue'
import { useChatContextStore } from '@/stores/chatContext'

/** Global Cmd/Ctrl+K opens the VoiceBot overlay from anywhere in the app; Escape closes it. */
export function useChatHotkey() {
  const chatContext = useChatContextStore()

  function onKeydown(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault()
      chatContext.toggleChat()
      return
    }
    if (e.key === 'Escape' && chatContext.open) {
      chatContext.closeChat()
    }
  }

  onMounted(() => window.addEventListener('keydown', onKeydown))
  onUnmounted(() => window.removeEventListener('keydown', onKeydown))
}
