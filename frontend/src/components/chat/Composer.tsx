import { LoaderCircle, Mic, MicOff, SendHorizontal, Square, X } from 'lucide-react'
import { useEffect, useRef, type FormEvent, type KeyboardEvent } from 'react'
import { MAX_RECORDING_SECONDS, type MicPermission, type RecorderPhase } from '../../hooks/useRecorder'

interface RecorderControls {
  supported: boolean
  phase: RecorderPhase
  permission: MicPermission
  seconds: number
  error: string | null
  start: () => void
  stop: () => void
  cancel: () => void
}

interface Props {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  busy: boolean
  recorder: RecorderControls
  /** Why voice input is off, if it is (for example, the server has no Sarvam key). */
  voiceDisabledReason: string | null
}

function formatTime(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

export default function Composer({ value, onChange, onSubmit, busy, recorder, voiceDisabledReason }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const recording = recorder.phase === 'recording'
  const requesting = recorder.phase === 'requesting'
  const canSend = value.trim().length > 0 && !busy && !recording

  // Grow the text box with its content, up to about five lines.
  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
  }, [value])

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    if (canSend) onSubmit()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) submit(event)
  }

  let micStatus: string | null = null
  if (!recorder.supported) micStatus = 'Voice input is not supported in this browser. Try a recent Chrome, Edge, Firefox or Safari.'
  else if (voiceDisabledReason) micStatus = voiceDisabledReason
  else if (requesting) micStatus = 'Waiting for microphone permission…'
  else if (recorder.error) micStatus = recorder.error
  else if (recorder.permission === 'denied') micStatus = "Microphone access is blocked. Allow it in your browser's site settings to ask by voice."

  const micDisabled = !recorder.supported || !!voiceDisabledReason || busy || requesting

  return (
    <form onSubmit={submit} className="border-t border-slate-200 bg-white px-3 pb-3 pt-3 sm:px-5 sm:pb-4">
      {recording ? (
        <div className="flex items-center gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3" role="status" aria-live="polite">
          <span className="relative flex h-3 w-3" aria-hidden="true">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-rose-500" />
          </span>
          <span className="flex-1 text-sm font-medium text-rose-900">
            Recording {formatTime(recorder.seconds)} / {formatTime(MAX_RECORDING_SECONDS)}
            <span className="hidden font-normal text-rose-800/80 sm:inline"> · Speak your question, then press stop.</span>
          </span>
          <button type="button" onClick={recorder.cancel} className="btn-ghost text-rose-900 hover:bg-rose-100" aria-label="Cancel recording">
            <X className="h-4 w-4" />
          </button>
          <button type="button" onClick={recorder.stop} className="btn-primary bg-rose-600 hover:bg-rose-700" aria-label="Stop recording and send">
            <Square className="h-3.5 w-3.5 fill-current" />
            <span className="hidden sm:inline">Stop &amp; send</span>
          </button>
        </div>
      ) : (
        <div className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm transition focus-within:border-bis-400 focus-within:ring-4 focus-within:ring-bis-100">
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <textarea
            id="question"
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={onKeyDown}
            maxLength={1000}
            placeholder="Ask about a product, an IS number or BIS certification…"
            className="max-h-40 min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-2 text-[0.95rem] leading-6 text-slate-900 placeholder:text-slate-400 focus:outline-none"
          />
          <button
            type="button"
            onClick={recorder.start}
            disabled={micDisabled}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-slate-600 transition-colors hover:bg-slate-100 hover:text-bis-700 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label={requesting ? 'Waiting for microphone permission' : 'Ask by voice'}
            title={micStatus ?? 'Ask by voice (up to 29 seconds)'}
          >
            {requesting ? (
              <LoaderCircle className="h-5 w-5 animate-spin" />
            ) : !recorder.supported || voiceDisabledReason || recorder.permission === 'denied' ? (
              <MicOff className="h-5 w-5" />
            ) : (
              <Mic className="h-5 w-5" />
            )}
          </button>
          <button type="submit" disabled={!canSend} className="btn-primary h-10 w-10 shrink-0 p-0 sm:w-auto sm:px-4" aria-label="Send question">
            {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
            <span className="hidden sm:inline">Send</span>
          </button>
        </div>
      )}
      <p className={`mt-2 px-1 text-xs ${micStatus && (recorder.error || recorder.permission === 'denied' || !recorder.supported) ? 'text-rose-700' : 'text-slate-500'}`} aria-live="polite">
        {micStatus ?? 'Press Enter to send, Shift + Enter for a new line. Answers come only from indexed BIS documents.'}
      </p>
    </form>
  )
}
