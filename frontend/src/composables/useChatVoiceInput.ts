import { computed, ref } from 'vue'
import { useVoiceRecorder } from './useVoiceRecorder'

/**
 * Owns the single continuous mic session for the VoiceBot overlay, plus the
 * confirm-before-send flow: speaking never submits anything by itself.
 * Roughly 2s after you stop talking, the transcript automatically appears in
 * `inputText` for review (or click "送出" in listening mode to trigger that
 * immediately, without waiting) — but only clicking "送出" again (or Enter)
 * in the review step actually calls `onSubmit`. This keeps background noise
 * or a misheard word from ever becoming an "out of scope" turn on its own,
 * while still not requiring a click just to stop talking.
 */
export function useChatVoiceInput(onSubmit: (text: string) => void | Promise<void>) {
  const inputText = ref('')
  const mode = ref<'listening' | 'reviewing' | 'typing'>('listening')
  const notice = ref<{ kind: 'failed'; text: string } | null>(null)
  const recorder = useVoiceRecorder()
  let noticeTimer: ReturnType<typeof setTimeout> | null = null
  /** True while the assistant is thinking about the last submission — the mic should sit idle rather than sample sound nobody's listening for. */
  const thinking = ref(false)

  const statusLabel = computed(() => {
    if (notice.value?.kind === 'failed') return notice.value.text
    if (thinking.value) return '理解中，暫停聆聽…'
    if (recorder.status.value === 'transcribing') return '辨識中…'
    if (recorder.isSpeaking.value) return '聆聽中，停頓約 2 秒後自動辨識'
    return '待命中，請開始說話'
  })

  function showNotice(text: string, durationMs: number) {
    if (noticeTimer) clearTimeout(noticeTimer)
    notice.value = { kind: 'failed', text }
    noticeTimer = setTimeout(() => (notice.value = null), durationMs)
  }

  /** Stops the current segment, transcribes it, and hands it to the user for review — never submits directly. */
  async function finishSpeaking() {
    notice.value = null
    const text = await recorder.stopAndTranscribe()
    if (!text) {
      showNotice(recorder.errorMessage.value ?? '還沒聽到聲音，請說話後再點擊「完成」。', 2400)
      recorder.resumeSegment()
      return
    }
    inputText.value = text
    mode.value = 'reviewing'
  }

  /** Discards the pending transcript and goes back to listening for another attempt. */
  function cancelReview() {
    inputText.value = ''
    mode.value = 'listening'
    recorder.resumeSegment()
  }

  /** Shared "送出" action for both typed text and a reviewed transcript. Pauses sensing for the duration of the request — no point listening for a next question while this one is still being answered. */
  async function confirmSend() {
    const text = inputText.value.trim()
    if (!text) return
    const cameFromVoice = mode.value === 'reviewing'
    inputText.value = ''
    if (cameFromVoice) {
      mode.value = 'listening'
      recorder.pauseSensing()
    }
    thinking.value = true
    try {
      await onSubmit(text)
    } finally {
      thinking.value = false
      if (cameFromVoice) recorder.resumeSegment()
    }
  }

  async function enterListening() {
    mode.value = 'listening'
    notice.value = null
    await recorder.startSession(() => finishSpeaking())
    if (recorder.status.value === 'error') {
      mode.value = 'typing'
      showNotice(recorder.errorMessage.value ?? '無法使用麥克風，請改用文字輸入。', 4000)
    }
  }

  function enterTyping() {
    recorder.stopSession()
    mode.value = 'typing'
    notice.value = null
  }

  function stop() {
    recorder.stopSession()
    if (noticeTimer) clearTimeout(noticeTimer)
    noticeTimer = null
  }

  return {
    inputText,
    mode,
    notice,
    thinking,
    recorder,
    statusLabel,
    finishSpeaking,
    cancelReview,
    confirmSend,
    enterListening,
    enterTyping,
    stop,
  }
}

export type ChatVoiceInput = ReturnType<typeof useChatVoiceInput>
