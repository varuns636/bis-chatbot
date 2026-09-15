import { BadgeCheck, CircleAlert, Languages, Mic, SearchX, Sparkles, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { languageTag } from '../../lib/languages'
import CitationList from './CitationList'
import FormattedAnswer from './FormattedAnswer'
import type { AssistantMessage, Message, UserMessage } from './types'

function UserBubble({ message }: { message: UserMessage }) {
  const text =
    message.status === 'transcribing'
      ? 'Transcribing your voice question…'
      : message.status === 'failed'
        ? 'Voice question (could not be transcribed)'
        : message.text
  return (
    <div className="flex animate-fade-up justify-end">
      <div className="max-w-[85%] sm:max-w-[75%]">
        <div
          className={`rounded-2xl rounded-br-md px-4 py-2.5 text-[0.95rem] leading-6 ${
            message.status === 'done' ? 'bg-bis-700 text-white' : 'bg-bis-100 italic text-bis-800'
          }`}
        >
          {text}
        </div>
        {message.voice && (
          <p className="mt-1 flex items-center justify-end gap-1 text-xs text-slate-500">
            <Mic className="h-3 w-3" aria-hidden="true" />
            Voice question
          </p>
        )}
      </div>
    </div>
  )
}

function AssistantAvatar() {
  return (
    <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-bis-50 text-bis-700" aria-hidden="true">
      <Sparkles className="h-4 w-4" />
    </span>
  )
}

function Pending({ voice }: { voice: boolean }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
      <span className="flex gap-1" aria-hidden="true">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-bis-400 [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-bis-400 [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-bis-400" />
      </span>
      {voice ? 'Transcribing, searching BIS documents and checking evidence…' : 'Searching BIS documents and checking evidence…'}
    </div>
  )
}

function Answer({ message }: { message: AssistantMessage }) {
  const [showEnglish, setShowEnglish] = useState(false)
  const response = message.response!
  const answer = response.answer.trim()

  return (
    <div className="min-w-0 flex-1 space-y-3 rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-4 shadow-sm sm:px-5">
      <div className="flex flex-wrap items-center gap-2">
        {response.evidence_found ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
            <BadgeCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Evidence found
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
            <SearchX className="h-3.5 w-3.5" aria-hidden="true" />
            Evidence not found
          </span>
        )}
        {response.translated && (
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
            <Languages className="h-3.5 w-3.5" aria-hidden="true" />
            Translated from the English answer
          </span>
        )}
      </div>

      {answer ? (
        <FormattedAnswer text={answer} lang={languageTag(response.language)} />
      ) : (
        <p className="text-sm italic text-slate-500">The assistant returned an empty answer. Please rephrase your question.</p>
      )}

      {!response.evidence_found && (
        <p className="text-xs text-slate-500">
          The indexed BIS documents do not support an answer to this question, so none was generated.
        </p>
      )}

      {response.warnings.length > 0 && (
        <div role="note" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-semibold text-amber-900">
            <TriangleAlert className="h-4 w-4" aria-hidden="true" />
            Verification warning
          </p>
          <ul className="mt-1.5 list-disc space-y-1 pl-6 text-sm text-amber-900/90">
            {response.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {response.citations.length > 0 && <CitationList citations={response.citations} />}

      {response.english_answer && response.english_answer !== response.answer && (
        <div>
          <button
            type="button"
            className="text-xs font-medium text-bis-700 underline-offset-2 hover:underline"
            aria-expanded={showEnglish}
            onClick={() => setShowEnglish((value) => !value)}
          >
            {showEnglish ? 'Hide the original English answer' : 'Show the original English answer'}
          </button>
          {showEnglish && (
            <div className="mt-2 rounded-lg bg-slate-50 p-3">
              <FormattedAnswer text={response.english_answer} lang="en" />
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-slate-400">
        Model: {response.model} · Searched for: “{response.search_query}”
      </p>
    </div>
  )
}

function ErrorCard({ message }: { message: AssistantMessage }) {
  const error = message.error!
  return (
    <div role="alert" className="flex-1 rounded-2xl rounded-bl-md border border-rose-200 bg-rose-50 px-4 py-3">
      <p className="flex items-center gap-2 text-sm font-semibold text-rose-900">
        <CircleAlert className="h-4 w-4" aria-hidden="true" />
        {error.title}
      </p>
      <p className="mt-1 text-sm text-rose-900/90">{error.message}</p>
      {error.hint && <p className="mt-2 font-mono text-xs text-rose-900/80">{error.hint}</p>}
    </div>
  )
}

function Streaming({ text, lang }: { text: string; lang: string }) {
  return (
    <div className="min-w-0 flex-1 rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-4 shadow-sm sm:px-5">
      <FormattedAnswer text={text} lang={lang} />
      <p className="mt-3 flex items-center gap-2 text-xs text-slate-400">
        <span className="h-2 w-2 animate-pulse rounded-full bg-bis-400" aria-hidden="true" />
        Writing the answer… citations are checked when it finishes.
      </p>
    </div>
  )
}

export default function MessageBubble({ message }: { message: Message }) {
  if (message.role === 'user') return <UserBubble message={message} />
  return (
    <div className="flex animate-fade-up gap-3">
      <AssistantAvatar />
      {message.status === 'pending' &&
        (message.streamingText ? (
          <Streaming text={message.streamingText} lang={languageTag(message.language)} />
        ) : (
          <Pending voice={message.voice} />
        ))}
      {message.status === 'error' && <ErrorCard message={message} />}
      {message.status === 'done' && <Answer message={message} />}
    </div>
  )
}
