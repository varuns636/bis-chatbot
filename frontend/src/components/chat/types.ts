import type { ChatResponse, Language } from '../../lib/api'

export interface FriendlyError {
  title: string
  message: string
  hint?: string
}

export type UserMessage = {
  id: string
  role: 'user'
  text: string
  voice: boolean
  status: 'done' | 'transcribing' | 'failed'
}

export type AssistantMessage = {
  id: string
  role: 'assistant'
  language: Language
  status: 'pending' | 'done' | 'error'
  voice: boolean
  /** English answer text received so far from /api/chat/stream, shown while the answer is written. */
  streamingText?: string
  response?: ChatResponse
  error?: FriendlyError
}

export type Message = UserMessage | AssistantMessage
