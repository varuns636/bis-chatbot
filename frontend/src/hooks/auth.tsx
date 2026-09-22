/**
 * Sign-in state for the BIS Assistant frontend.
 *
 * The session lives only in this browser (localStorage). There is no auth backend: the login page
 * checks the phone number, the one-time code and the Gmail address itself, and the API is open to
 * everyone. Guest mode is a session like any other, with `method: 'guest'`.
 *
 * To move to real accounts later, replace signInWithPhone / signInWithGoogle with calls to the
 * backend and keep the rest of the context the same.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type SignInMethod = 'phone' | 'google' | 'guest'

export interface User {
  /** Stable id for this browser's session. */
  id: string
  /** Name shown in the navbar. */
  name: string
  method: SignInMethod
  /** 10-digit Indian phone number, for `method: 'phone'`. */
  phone?: string
  /** Gmail address, for `method: 'google'`. */
  email?: string
  /** When the session started (ISO 8601). */
  signedInAt: string
}

interface AuthContextValue {
  user: User | null
  /** True until the stored session has been read, so guards do not redirect too early. */
  loading: boolean
  isGuest: boolean
  signInWithPhone: (phone: string) => User
  signInWithGoogle: (email: string) => User
  continueAsGuest: () => User
  signOut: () => void
}

const STORAGE_KEY = 'bis-assistant.session'

const AuthContext = createContext<AuthContextValue | null>(null)

/** A 10-digit Indian mobile number, with an optional +91 / 0 prefix and spaces or dashes. */
export const PHONE_PATTERN = /^(?:\+?91[\s-]?|0)?([6-9]\d{9})$/
/** A Gmail address. Other providers are rejected, because the button says "Continue with Gmail". */
export const GMAIL_PATTERN = /^[a-zA-Z0-9](?:[a-zA-Z0-9._%+-]*[a-zA-Z0-9])?@gmail\.com$/i

/** The 10 digits of a phone number, without the country code. Returns "" if the number is invalid. */
export function normalizePhone(value: string): string {
  return PHONE_PATTERN.exec(value.trim())?.[1] ?? ''
}

function isUser(value: unknown): value is User {
  const user = value as User | null
  return (
    !!user &&
    typeof user.id === 'string' &&
    typeof user.name === 'string' &&
    (user.method === 'phone' || user.method === 'google' || user.method === 'guest')
  )
}

function readStoredUser(): User | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    return isUser(parsed) ? parsed : null
  } catch {
    // Private browsing, or a session written by an older version of the app.
    return null
  }
}

function writeStoredUser(user: User | null): void {
  try {
    if (user) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(user))
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage can be blocked. The session then lasts until the page is reloaded.
  }
}

function newId(): string {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/** "priya.sharma@gmail.com" becomes "Priya Sharma". */
function nameFromEmail(email: string): string {
  return (
    email
      .split('@')[0]
      .split(/[._-]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ') || email
  )
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setUser(readStoredUser())
    setLoading(false)
  }, [])

  const startSession = useCallback((partial: Omit<User, 'id' | 'signedInAt'>): User => {
    const session: User = { ...partial, id: newId(), signedInAt: new Date().toISOString() }
    writeStoredUser(session)
    setUser(session)
    return session
  }, [])

  const signInWithPhone = useCallback(
    (phone: string) => {
      const digits = normalizePhone(phone) || phone.trim()
      return startSession({ name: `+91 ${digits}`, method: 'phone', phone: digits })
    },
    [startSession],
  )

  const signInWithGoogle = useCallback(
    (email: string) => {
      const address = email.trim().toLowerCase()
      return startSession({ name: nameFromEmail(address), method: 'google', email: address })
    },
    [startSession],
  )

  const continueAsGuest = useCallback(() => startSession({ name: 'Guest', method: 'guest' }), [startSession])

  const signOut = useCallback(() => {
    writeStoredUser(null)
    setUser(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isGuest: user?.method === 'guest',
      signInWithPhone,
      signInWithGoogle,
      continueAsGuest,
      signOut,
    }),
    [user, loading, signInWithPhone, signInWithGoogle, continueAsGuest, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}
