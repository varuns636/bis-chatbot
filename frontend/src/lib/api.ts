/**
 * Client for the BIS Assistant FastAPI backend (src/api.py).
 *
 * The browser only talks to FastAPI. Sarvam AI (speech-to-text and translation) is called by the
 * backend, so no Sarvam key or URL ever appears in the frontend.
 */

export type Language = 'english' | 'kannada' | 'hindi'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')

/** A citation that the backend verified against the retrieved evidence. */
export interface Citation {
  source: string
  page: number
  standard: string
  title: string
  preview: string
}

/** POST /api/chat response (ChatResponse in src/api.py). */
export interface ChatResponse {
  answer: string
  language: Language
  citations: Citation[]
  evidence_found: boolean
  model: string
  search_query: string
  warnings: string[]
  english_answer: string | null
  translated: boolean
}

/** POST /api/voice-chat response (VoiceChatResponse in src/api.py). */
export interface VoiceChatResponse extends ChatResponse {
  transcript: string
  stt_provider: string
  llm_provider: string
}

/** POST /api/speech-to-text response (SpeechToTextResponse in src/api.py). */
export interface SpeechToTextResponse {
  transcript: string
  language: Language
  language_code: string
  provider: string
}

/** GET /api/status response. */
export interface StatusResponse {
  llm: { provider: string; model: string; available: boolean; error: string | null }
  stt: { provider: string; model: string; configured: boolean }
  translation: { provider: string; model: string; configured: boolean }
  index: { chunks: number; documents: string[]; unavailable_files: Record<string, string> }
  supported_languages: Record<Language, string>
}

export interface ChatRequest {
  question: string
  language: Language
  /** Earlier user questions, oldest first. Used to resolve follow-ups such as "what about marking?". */
  history: string[]
}

/** One line of the POST /api/chat/stream response. */
type StreamEvent =
  | { type: 'token'; text: string }
  | { type: 'done'; response: ChatResponse }
  | { type: 'error'; status: number; detail: string }

/** What went wrong, so the UI can explain it. */
export type ApiErrorKind =
  | 'network' // backend not reachable or timed out
  | 'validation' // HTTP 400 / 413 / 422
  | 'speech' // HTTP 502: Sarvam failed
  | 'voice-config' // HTTP 503 about SARVAM_API_KEY
  | 'llm' // HTTP 503: Ollama not running or model missing
  | 'server' // anything else

export class ApiError extends Error {
  readonly status: number | null
  readonly kind: ApiErrorKind

  constructor(message: string, status: number | null, kind: ApiErrorKind) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.kind = kind
  }
}

const ANSWER_TIMEOUT_MS = 180_000 // local LLM answers can take 10-30 s; allow for slow machines
const QUICK_TIMEOUT_MS = 8_000

function errorKind(status: number, message: string): ApiErrorKind {
  if (status === 400 || status === 413 || status === 422) return 'validation'
  if (status === 502) return 'speech'
  if (status === 503) return /SARVAM_API_KEY/.test(message) ? 'voice-config' : 'llm'
  return 'server'
}

function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{ loc, msg, type }, ...]
    const messages = detail.map((item) => (item as { msg?: string })?.msg).filter(Boolean)
    if (messages.length) return messages.join('; ')
  }
  return `The server returned HTTP ${status}.`
}

function networkError(error: unknown): ApiError {
  const timedOut = error instanceof DOMException && error.name === 'AbortError'
  return new ApiError(
    timedOut
      ? 'The backend took too long to answer. Please try again.'
      : `Cannot reach the BIS Assistant backend at ${API_BASE_URL}.`,
    null,
    'network',
  )
}

async function httpError(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null)
  const message = errorMessage(response.status, body)
  return new ApiError(message, response.status, errorKind(response.status, message))
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = ANSWER_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, signal: controller.signal })
  } catch (error) {
    throw networkError(error)
  } finally {
    window.clearTimeout(timer)
  }

  if (!response.ok) throw await httpError(response)
  return (await response.json()) as T
}

export function getHealth(): Promise<{ status: string }> {
  return request('/api/health', {}, QUICK_TIMEOUT_MS)
}

export function getStatus(): Promise<StatusResponse> {
  return request('/api/status', {}, QUICK_TIMEOUT_MS)
}

export function sendChat(body: ChatRequest): Promise<ChatResponse> {
  return request('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/chat/stream. Calls `onToken` with each piece of an English answer as the local model
 * writes it, then resolves with the full, checked response (the same body /api/chat returns).
 * Kannada and Hindi answers arrive only in the final response, after translation.
 */
export async function streamChat(body: ChatRequest, onToken: (text: string) => void): Promise<ChatResponse> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), ANSWER_TIMEOUT_MS)
  try {
    let response: Response
    try {
      response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } catch (error) {
      throw networkError(error)
    }
    if (!response.ok || !response.body) throw await httpError(response)

    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
    let buffer = ''
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += value
      let newline: number
      while ((newline = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, newline).trim()
        buffer = buffer.slice(newline + 1)
        if (!line) continue
        const event = JSON.parse(line) as StreamEvent
        if (event.type === 'token') onToken(event.text)
        else if (event.type === 'done') return event.response
        else throw new ApiError(event.detail, event.status, errorKind(event.status, event.detail))
      }
    }
    throw new ApiError('The answer stream ended unexpectedly. Please try again.', null, 'server')
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw networkError(error)
  } finally {
    window.clearTimeout(timer)
  }
}

const AUDIO_EXTENSIONS: Record<string, string> = {
  'audio/webm': 'webm',
  'audio/ogg': 'ogg',
  'audio/mp4': 'm4a',
  'audio/mpeg': 'mp3',
  'audio/wav': 'wav',
}

/** Wrap a recording as a file with a plain MIME type ("audio/webm", not "audio/webm;codecs=opus"). */
function audioFile(audio: Blob): File {
  const type = audio.type.split(';')[0] || 'audio/webm'
  return new File([audio], `question.${AUDIO_EXTENSIONS[type] ?? 'webm'}`, { type })
}

export function speechToText(audio: Blob, language: Language): Promise<SpeechToTextResponse> {
  const form = new FormData()
  form.append('file', audioFile(audio))
  form.append('language', language)
  return request('/api/speech-to-text', { method: 'POST', body: form })
}

export function voiceChat(audio: Blob, language: Language, history: string[]): Promise<VoiceChatResponse> {
  const form = new FormData()
  form.append('file', audioFile(audio))
  form.append('language', language)
  history.forEach((question) => form.append('history', question))
  return request('/api/voice-chat', { method: 'POST', body: form })
}
