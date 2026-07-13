import { ref, shallowRef } from 'vue'

export type RecorderStatus = 'idle' | 'listening' | 'transcribing' | 'error'

const BAR_COUNT = 16
const SPEAKING_RMS = 0.1
const SILENCE_AUTO_MS = 2000

/**
 * Continuous mic session with NO automatic submission. Transcription CAN
 * trigger automatically (`onAutoFinish`, after ~2s of silence following real
 * speech) so the user doesn't have to click anything just to see the
 * transcript — but that only ever populates the review text, it never
 * submits. Only an explicit "送出" click in the review step calls the
 * chat's onSubmit. That split is deliberate: background noise should never
 * turn into an "out of scope" turn on its own, but the user also shouldn't
 * have to click a button just to stop talking.
 */
export function useVoiceRecorder() {
  const status = ref<RecorderStatus>('idle')
  const errorMessage = ref<string | null>(null)
  const levels = ref<number[]>(new Array(BAR_COUNT).fill(0))
  const isSpeaking = ref(false)
  /** True once the current segment has crossed the speaking threshold at least once — gates the "finish" action so an accidental click on pure silence doesn't waste an STT call. */
  const hasPendingSpeech = ref(false)
  /** Exposed so a visualizer component (e.g. SiriWaveform) can run its own independent draw loop off the same live analyser. */
  const analyserRef = shallowRef<AnalyserNode | null>(null)

  let stream: MediaStream | null = null
  let audioContext: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let mediaRecorder: MediaRecorder | null = null
  let chunks: Blob[] = []
  let rafId: number | null = null
  let sessionActive = false
  let silenceStartedAt: number | null = null
  let autoFinishTriggered = false
  let onAutoFinish: (() => void) | null = null

  function resetVisuals() {
    levels.value = new Array(BAR_COUNT).fill(0)
    isSpeaking.value = false
  }

  function teardownStream() {
    stream?.getTracks().forEach((t) => t.stop())
    stream = null
    void audioContext?.close()
    audioContext = null
    analyser = null
    analyserRef.value = null
  }

  function tick() {
    if (!analyser) return
    const freq = new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteFrequencyData(freq)
    const bucket = Math.floor(freq.length / BAR_COUNT) || 1
    levels.value = levels.value.map((_, i) => {
      let sum = 0
      for (let j = i * bucket; j < (i + 1) * bucket && j < freq.length; j++) sum += freq[j]
      return Math.min(1, sum / bucket / 255)
    })

    const time = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(time)
    let sumSq = 0
    for (let i = 0; i < time.length; i++) {
      const v = (time[i] - 128) / 128
      sumSq += v * v
    }
    const rms = Math.sqrt(sumSq / time.length)
    isSpeaking.value = rms >= SPEAKING_RMS

    const now = performance.now()
    if (isSpeaking.value) {
      hasPendingSpeech.value = true
      silenceStartedAt = null
    } else if (silenceStartedAt === null) {
      silenceStartedAt = now
    }

    if (
      hasPendingSpeech.value &&
      !autoFinishTriggered &&
      silenceStartedAt !== null &&
      now - silenceStartedAt >= SILENCE_AUTO_MS
    ) {
      autoFinishTriggered = true
      onAutoFinish?.()
      return
    }

    rafId = requestAnimationFrame(tick)
  }

  function startSegment() {
    if (!stream) return
    chunks = []
    hasPendingSpeech.value = false
    silenceStartedAt = null
    autoFinishTriggered = false
    mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data)
    }
    mediaRecorder.start()
    status.value = 'listening'
    rafId = requestAnimationFrame(tick)
  }

  async function transcribeBlob(blob: Blob): Promise<string | null> {
    try {
      const res = await fetch('/api/stt', { method: 'POST', headers: { 'Content-Type': blob.type }, body: blob })
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.error ?? 'STT failed')
      const { text } = (await res.json()) as { text: string }
      return text.trim() || null
    } catch (err) {
      errorMessage.value = err instanceof Error ? err.message : '語音辨識失敗'
      return null
    }
  }

  /** Stops the current segment and transcribes it. Does NOT resume recording or submit anything — call `resumeSegment()` explicitly once the caller is done with the result. Returns null without an STT call if nothing was actually said. */
  function stopAndTranscribe(): Promise<string | null> {
    return new Promise((resolve) => {
      errorMessage.value = null
      if (!sessionActive || !mediaRecorder || mediaRecorder.state !== 'recording') {
        resolve(null)
        return
      }
      if (!hasPendingSpeech.value) {
        resolve(null)
        return
      }
      if (rafId !== null) cancelAnimationFrame(rafId)
      rafId = null
      const recorder = mediaRecorder
      const mimeType = recorder.mimeType || 'audio/webm'
      status.value = 'transcribing'
      resetVisuals()
      recorder.onstop = async () => {
        const blob = chunks.length ? new Blob(chunks, { type: mimeType }) : null
        const text = blob ? await transcribeBlob(blob) : null
        status.value = 'idle'
        resolve(text)
      }
      recorder.stop()
    })
  }

  /** Starts a fresh recording segment on the already-acquired mic stream — call after the caller has handled (sent or discarded) the previous transcript. */
  function resumeSegment() {
    if (!sessionActive) return
    startSegment()
  }

  /** Stops sampling and discards whatever's mid-recording, WITHOUT releasing the mic stream — for pausing while the assistant is thinking, not for ending the session. Call `resumeSegment()` to pick back up. */
  function pauseSensing() {
    if (rafId !== null) cancelAnimationFrame(rafId)
    rafId = null
    if (mediaRecorder?.state === 'recording') {
      mediaRecorder.onstop = null
      mediaRecorder.stop()
    }
    mediaRecorder = null
    resetVisuals()
    status.value = 'idle'
  }

  async function startSession(autoFinishCallback: () => void) {
    if (sessionActive) return
    errorMessage.value = null
    onAutoFinish = autoFinishCallback
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      audioContext = new AudioContext()
      const source = audioContext.createMediaStreamSource(stream)
      analyser = audioContext.createAnalyser()
      analyser.fftSize = 512
      source.connect(analyser)
      analyserRef.value = analyser
      // AudioContexts created from a Vue watcher callback (not a direct
      // click handler) sometimes start 'suspended' under browser autoplay
      // policy — without this the analyser silently reads all-zero data and
      // speech would never register.
      if (audioContext.state === 'suspended') await audioContext.resume()
      sessionActive = true
      startSegment()
    } catch (err) {
      status.value = 'error'
      errorMessage.value = err instanceof Error ? err.message : '無法取得麥克風權限'
      teardownStream()
    }
  }

  function stopSession() {
    sessionActive = false
    onAutoFinish = null
    if (rafId !== null) cancelAnimationFrame(rafId)
    rafId = null
    if (mediaRecorder?.state === 'recording') {
      mediaRecorder.onstop = () => {
        teardownStream()
        resetVisuals()
        status.value = 'idle'
      }
      mediaRecorder.stop()
    } else {
      teardownStream()
      resetVisuals()
      status.value = 'idle'
    }
  }

  return {
    status,
    errorMessage,
    levels,
    isSpeaking,
    hasPendingSpeech,
    analyser: analyserRef,
    startSession,
    stopSession,
    stopAndTranscribe,
    resumeSegment,
    pauseSensing,
  }
}
