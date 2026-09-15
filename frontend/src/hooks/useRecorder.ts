import { useCallback, useEffect, useRef, useState } from 'react'

export type RecorderPhase = 'idle' | 'requesting' | 'recording'
export type MicPermission = 'unknown' | 'prompt' | 'granted' | 'denied' | 'unsupported'

/** Sarvam's speech-to-text REST API accepts recordings under 30 seconds. */
export const MAX_RECORDING_SECONDS = 29

// Formats Sarvam accepts, in order of preference. Chrome and Firefox record WebM/Opus, Safari MP4.
const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']

function isSupported(): boolean {
  return typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'
}

/** Records one voice question with MediaRecorder and hands the audio to `onRecorded`. */
export function useRecorder(onRecorded: (audio: Blob) => void) {
  const supported = isSupported()
  const [phase, setPhase] = useState<RecorderPhase>('idle')
  const [permission, setPermission] = useState<MicPermission>(supported ? 'unknown' : 'unsupported')
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<number | undefined>(undefined)
  const discardRef = useRef(false)
  const onRecordedRef = useRef(onRecorded)

  useEffect(() => {
    onRecordedRef.current = onRecorded
  }, [onRecorded])

  // Show the microphone permission where the browser exposes it (Chrome, Edge, Firefox).
  useEffect(() => {
    if (!supported || !navigator.permissions?.query) return
    let permissionStatus: PermissionStatus | undefined
    navigator.permissions
      .query({ name: 'microphone' as PermissionName })
      .then((result) => {
        permissionStatus = result
        setPermission(result.state)
        result.onchange = () => setPermission(result.state)
      })
      .catch(() => {})
    return () => {
      if (permissionStatus) permissionStatus.onchange = null
    }
  }, [supported])

  const release = useCallback(() => {
    window.clearInterval(timerRef.current)
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    recorderRef.current = null
  }, [])

  const stop = useCallback(() => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }, [])

  const cancel = useCallback(() => {
    discardRef.current = true
    stop()
  }, [stop])

  const start = useCallback(async () => {
    if (!supported || recorderRef.current) return
    setError(null)
    setPhase('requesting')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      setPermission('granted')
      streamRef.current = stream
      const mimeType = MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type))
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      chunksRef.current = []
      discardRef.current = false

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onstop = () => {
        const audio = new Blob(chunksRef.current, { type: recorder.mimeType || mimeType || 'audio/webm' })
        release()
        setPhase('idle')
        setSeconds(0)
        if (discardRef.current) return
        if (audio.size > 0) onRecordedRef.current(audio)
        else setError('No audio was recorded. Please try again.')
      }

      recorder.start()
      recorderRef.current = recorder
      setPhase('recording')
      setSeconds(0)
      const startedAt = Date.now()
      timerRef.current = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - startedAt) / 1000)
        setSeconds(elapsed)
        if (elapsed >= MAX_RECORDING_SECONDS && recorder.state === 'recording') recorder.stop()
      }, 250)
    } catch (err) {
      release()
      setPhase('idle')
      const name = err instanceof DOMException ? err.name : ''
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        setPermission('denied')
        setError("Microphone access is blocked. Allow it in your browser's site settings, then try again.")
      } else if (name === 'NotFoundError') {
        setError('No microphone was found on this device.')
      } else {
        setError('The microphone could not be started. Please try again.')
      }
    }
  }, [supported, release])

  // Stop recording if the page unmounts.
  useEffect(
    () => () => {
      discardRef.current = true
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
      release()
    },
    [release],
  )

  return { supported, phase, permission, seconds, error, start, stop, cancel, clearError: () => setError(null) }
}
