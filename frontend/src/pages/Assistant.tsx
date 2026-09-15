import { BookOpenText, CircleAlert, Cpu, FileWarning, Mic, RefreshCw, Sparkles, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import Composer from '../components/chat/Composer'
import LanguageSelector from '../components/chat/LanguageSelector'
import MessageBubble from '../components/chat/MessageBubble'
import type { AssistantMessage, FriendlyError, Message, UserMessage } from '../components/chat/types'
import Navbar from '../components/Navbar'
import StatusIndicator from '../components/StatusIndicator'
import { useBackendStatus } from '../hooks/backendStatus'
import { useRecorder } from '../hooks/useRecorder'
import { API_BASE_URL, ApiError, streamChat, voiceChat, type Language } from '../lib/api'
import { isLanguage } from '../lib/languages'

const EXAMPLE_QUESTIONS = [
  'What is IS 14543?',
  'What are the requirements for packaged drinking water?',
  'What is IS 7098 related to?',
  'What are the requirements for electrical cables?',
]
const LANGUAGE_STORAGE_KEY = 'bis-assistant-language'
const HISTORY_LENGTH = 5
const BACKEND_COMMAND = 'uvicorn src.api:app --reload --port 8000'

function loadLanguage(): Language {
  try {
    const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY)
    if (isLanguage(saved)) return saved
  } catch {
    // Storage can be blocked; English is a fine default.
  }
  return 'english'
}

function describeError(error: unknown): FriendlyError {
  if (!(error instanceof ApiError)) {
    return { title: 'Something went wrong', message: 'An unexpected error occurred. Please try again.' }
  }
  switch (error.kind) {
    case 'network':
      return {
        title: 'Backend unavailable',
        message: `${error.message} Make sure the FastAPI server is running.`,
        hint: BACKEND_COMMAND,
      }
    case 'llm':
      return { title: 'Local AI model unavailable', message: error.message }
    case 'speech':
      return { title: 'Speech service failed', message: error.message }
    case 'voice-config':
      return { title: 'Voice input is not configured', message: error.message }
    case 'validation':
      return { title: 'Request not accepted', message: error.message }
    default:
      return { title: 'Server error', message: error.message }
  }
}

let nextId = 0
const newId = () => `m${Date.now()}-${nextId++}`

function EmptyState({ onPick, disabled }: { onPick: (question: string) => void; disabled: boolean }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center py-8 text-center sm:py-14">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-bis-50 text-bis-700">
        <Sparkles className="h-7 w-7" aria-hidden="true" />
      </span>
      <h1 className="mt-5 text-2xl font-semibold tracking-tight text-slate-900">Ask about Indian Standards</h1>
      <p className="mt-2 max-w-md text-sm leading-6 text-slate-600">
        Get answers from indexed BIS documents, with the PDF page for every point. Type, or use the microphone to ask by
        voice.
      </p>
      <div className="mt-8 grid w-full gap-3 sm:grid-cols-2">
        {EXAMPLE_QUESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            disabled={disabled}
            onClick={() => onPick(question)}
            className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm font-medium text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-bis-300 hover:text-bis-800 hover:shadow disabled:cursor-not-allowed disabled:opacity-50"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  )
}

function KnowledgePanel() {
  const { state, status, refresh } = useBackendStatus()
  return (
    <div className="card space-y-5 p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">Knowledge base</h2>
        <button type="button" onClick={refresh} className="btn-ghost p-1.5" aria-label="Check the backend connection again">
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
      <StatusIndicator />

      {state === 'connected' && status ? (
        <>
          <ul className="space-y-2">
            {status.index.documents.map((title) => (
              <li key={title} className="flex gap-2 text-xs leading-5 text-slate-600">
                <BookOpenText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-bis-600" aria-hidden="true" />
                {title}
              </li>
            ))}
          </ul>
          {Object.keys(status.index.unavailable_files).length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-700">Not searchable</h3>
              <ul className="mt-2 space-y-2">
                {Object.entries(status.index.unavailable_files).map(([file, reason]) => (
                  <li key={file} className="flex gap-2 text-xs leading-5 text-slate-500">
                    <FileWarning className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden="true" />
                    <span>
                      <span className="font-mono">{file}</span>: {reason}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <dl className="space-y-2 border-t border-slate-100 pt-4 text-xs">
            <div className="flex items-center justify-between gap-2">
              <dt className="flex items-center gap-1.5 text-slate-500">
                <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
                Answer model
              </dt>
              <dd className={status.llm.available ? 'font-medium text-slate-700' : 'font-medium text-rose-700'}>
                {status.llm.model} {status.llm.available ? '' : '(offline)'}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="flex items-center gap-1.5 text-slate-500">
                <Mic className="h-3.5 w-3.5" aria-hidden="true" />
                Voice input
              </dt>
              <dd className="font-medium text-slate-700">{status.stt.configured ? 'Available' : 'Not configured'}</dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-slate-500">Indexed passages</dt>
              <dd className="font-medium text-slate-700">{status.index.chunks}</dd>
            </div>
          </dl>
        </>
      ) : (
        <p className="text-xs leading-5 text-slate-500">
          {state === 'checking' ? 'Connecting to the backend…' : 'Start the backend to see the indexed documents.'}
        </p>
      )}
      <p className="border-t border-slate-100 pt-4 text-xs leading-5 text-slate-500">
        For official decisions, always verify the latest information with BIS.
      </p>
    </div>
  )
}

export default function Assistant() {
  const { state, status } = useBackendStatus()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [language, setLanguage] = useState<Language>(loadLanguage)
  const bottomRef = useRef<HTMLDivElement>(null)

  const busy = messages.some(
    (message) =>
      (message.role === 'assistant' && message.status === 'pending') ||
      (message.role === 'user' && message.status === 'transcribing'),
  )

  useEffect(() => {
    try {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, language)
    } catch {
      // Ignore blocked storage.
    }
  }, [language])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  const update = useCallback(<T extends Message>(id: string, changes: Partial<T>) => {
    setMessages((current) => current.map((message) => (message.id === id ? ({ ...message, ...changes } as Message) : message)))
  }, [])

  // Earlier questions let the backend resolve follow-ups such as "what does it say about marking?".
  const previousQuestions = (current: Message[]) =>
    current
      .filter((message): message is UserMessage => message.role === 'user' && message.status === 'done')
      .map((message) => message.text)
      .slice(-HISTORY_LENGTH)

  const ask = async (question: string) => {
    const text = question.trim()
    if (!text || busy) return
    const history = previousQuestions(messages)
    const assistantId = newId()
    setMessages((current) => [
      ...current,
      { id: newId(), role: 'user', text, voice: false, status: 'done' },
      { id: assistantId, role: 'assistant', language, status: 'pending', voice: false },
    ])
    setInput('')
    try {
      const response = await streamChat({ question: text, language, history }, (token) =>
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId && message.role === 'assistant'
              ? { ...message, streamingText: (message.streamingText ?? '') + token }
              : message,
          ),
        ),
      )
      update<AssistantMessage>(assistantId, { status: 'done', response, streamingText: undefined })
    } catch (error) {
      update<AssistantMessage>(assistantId, { status: 'error', error: describeError(error) })
    }
  }

  const askByVoice = async (audio: Blob) => {
    const history = previousQuestions(messages)
    const userId = newId()
    const assistantId = newId()
    setMessages((current) => [
      ...current,
      { id: userId, role: 'user', text: '', voice: true, status: 'transcribing' },
      { id: assistantId, role: 'assistant', language, status: 'pending', voice: true },
    ])
    try {
      const response = await voiceChat(audio, language, history)
      update<UserMessage>(userId, { text: response.transcript, status: 'done' })
      update<AssistantMessage>(assistantId, { status: 'done', response })
    } catch (error) {
      update<UserMessage>(userId, { status: 'failed' })
      update<AssistantMessage>(assistantId, { status: 'error', error: describeError(error) })
    }
  }

  const recorder = useRecorder((audio) => void askByVoice(audio))
  const voiceDisabledReason =
    status && !status.stt.configured ? 'Voice input is not configured on the server (SARVAM_API_KEY is missing).' : null

  return (
    <div className="flex h-dvh flex-col bg-slate-50">
      <Navbar />
      <div className="mx-auto flex w-full max-w-6xl flex-1 gap-6 overflow-hidden px-2 py-3 sm:px-6 sm:py-5">
        <section
          id="main"
          aria-label="Conversation"
          className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
        >
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-3 py-3 sm:px-5">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-900">BIS Assistant</p>
              <p className="text-xs text-slate-500">Answer language</p>
            </div>
            <div className="flex items-center gap-2">
              <LanguageSelector value={language} onChange={setLanguage} disabled={busy} />
              <button
                type="button"
                onClick={() => setMessages([])}
                disabled={messages.length === 0 || busy}
                className="btn-ghost"
                aria-label="Clear conversation"
                title="Clear conversation"
              >
                <Trash2 className="h-4 w-4" />
                <span className="hidden sm:inline">Clear</span>
              </button>
            </div>
          </div>

          {state === 'unavailable' && (
            <div role="alert" className="flex gap-3 border-b border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900 sm:px-5">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <p>
                The backend at <span className="font-mono">{API_BASE_URL}</span> is not reachable. Start it with{' '}
                <code className="rounded bg-rose-100 px-1 py-0.5 font-mono text-xs">{BACKEND_COMMAND}</code>
              </p>
            </div>
          )}

          <div className="flex-1 overflow-y-auto px-3 py-5 sm:px-6" role="log" aria-live="polite" aria-label="Messages">
            {messages.length === 0 ? (
              <EmptyState onPick={(question) => void ask(question)} disabled={busy} />
            ) : (
              <div className="mx-auto max-w-3xl space-y-5">
                {messages.map((message) => (
                  <MessageBubble key={message.id} message={message} />
                ))}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <Composer
            value={input}
            onChange={setInput}
            onSubmit={() => void ask(input)}
            busy={busy}
            recorder={recorder}
            voiceDisabledReason={voiceDisabledReason}
          />
        </section>

        <aside className="hidden w-72 shrink-0 overflow-y-auto lg:block" aria-label="Knowledge base">
          <KnowledgePanel />
        </aside>
      </div>
    </div>
  )
}
