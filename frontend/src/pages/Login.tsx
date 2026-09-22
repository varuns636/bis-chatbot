/**
 * Sign-in page: phone number with a one-time code, Gmail address, or guest mode.
 *
 * The session is stored in this browser only (see src/hooks/auth.tsx). No password, code or
 * address is sent anywhere, and the one-time code is generated and checked in the page itself,
 * so it is shown on screen. Guest mode gives the same access as a signed-in user.
 */

import { ArrowLeft, ArrowRight, Check, Mail, Phone, ShieldCheck, UserRound } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import Logo from '../components/Logo'
import StatusIndicator from '../components/StatusIndicator'
import { GMAIL_PATTERN, PHONE_PATTERN, normalizePhone, useAuth } from '../hooks/auth'

type Tab = 'phone' | 'google'

const CODE_LENGTH = 6
/** How long a one-time code stays valid, in seconds. */
const CODE_TTL_SECONDS = 120

function randomCode(): string {
  return String(Math.floor(Math.random() * 10 ** CODE_LENGTH)).padStart(CODE_LENGTH, '0')
}

function TabButton({ active, onClick, icon: Icon, label }: {
  active: boolean
  onClick: () => void
  icon: typeof Phone
  label: string
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
        active ? 'bg-white text-bis-800 shadow-sm' : 'text-slate-600 hover:text-slate-900'
      }`}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
    </button>
  )
}

/** Step 1 of phone sign-in: the number. Step 2: the code. */
function PhoneForm({ onDone }: { onDone: (phone: string) => void }) {
  const [phone, setPhone] = useState('')
  const [sentCode, setSentCode] = useState('')
  const [sentAt, setSentAt] = useState(0)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [secondsLeft, setSecondsLeft] = useState(0)
  const codeInput = useRef<HTMLInputElement>(null)

  // Count the code's remaining validity down to zero.
  useEffect(() => {
    if (!sentAt) return
    const tick = () => setSecondsLeft(Math.max(0, CODE_TTL_SECONDS - Math.round((Date.now() - sentAt) / 1000)))
    tick()
    const timer = window.setInterval(tick, 1000)
    return () => window.clearInterval(timer)
  }, [sentAt])

  useEffect(() => {
    if (sentCode) codeInput.current?.focus()
  }, [sentCode])

  const sendCode = (event: FormEvent) => {
    event.preventDefault()
    if (!PHONE_PATTERN.test(phone.trim())) {
      setError('Enter a 10-digit Indian mobile number, for example 98765 43210.')
      return
    }
    setError('')
    setCode('')
    setSentCode(randomCode())
    setSentAt(Date.now())
  }

  const verify = (event: FormEvent) => {
    event.preventDefault()
    if (secondsLeft === 0) {
      setError('The code has expired. Send a new one.')
      return
    }
    if (code.trim() !== sentCode) {
      setError('That code does not match. Check the code above and try again.')
      return
    }
    onDone(phone)
  }

  if (!sentCode) {
    return (
      <form onSubmit={sendCode} className="space-y-4" noValidate>
        <div>
          <label htmlFor="phone" className="block text-sm font-medium text-slate-700">
            Mobile number
          </label>
          <div className="mt-1.5 flex rounded-xl border border-slate-300 bg-white shadow-sm focus-within:border-bis-500">
            <span className="flex items-center border-r border-slate-200 px-3 text-sm font-medium text-slate-500">
              +91
            </span>
            <input
              id="phone"
              name="phone"
              type="tel"
              inputMode="numeric"
              autoComplete="tel"
              autoFocus
              placeholder="98765 43210"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              aria-invalid={!!error}
              aria-describedby={error ? 'phone-error' : undefined}
              className="w-full rounded-r-xl px-3 py-2.5 text-sm text-slate-900 outline-none placeholder:text-slate-400"
            />
          </div>
          {error && (
            <p id="phone-error" role="alert" className="mt-2 text-sm text-red-600">
              {error}
            </p>
          )}
        </div>
        <button type="submit" className="btn-primary w-full py-3">
          Send one-time code
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </form>
    )
  }

  return (
    <form onSubmit={verify} className="space-y-4" noValidate>
      <div className="rounded-xl border border-bis-200 bg-bis-50 px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-bis-700">Demo code</p>
        <p className="mt-1 font-mono text-2xl tracking-[0.3em] text-bis-900">{sentCode}</p>
        <p className="mt-1 text-xs text-bis-800">
          No SMS is sent. The code is generated in your browser and{' '}
          {secondsLeft > 0 ? `expires in ${secondsLeft}s.` : 'has expired.'}
        </p>
      </div>

      <div>
        <label htmlFor="code" className="block text-sm font-medium text-slate-700">
          Enter the code sent to +91 {normalizePhone(phone) || phone}
        </label>
        <input
          id="code"
          ref={codeInput}
          name="one-time-code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={CODE_LENGTH}
          placeholder="000000"
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
          aria-invalid={!!error}
          aria-describedby={error ? 'code-error' : undefined}
          className="mt-1.5 w-full rounded-xl border border-slate-300 px-3 py-2.5 text-center font-mono text-lg tracking-[0.4em] text-slate-900 shadow-sm outline-none focus:border-bis-500"
        />
        {error && (
          <p id="code-error" role="alert" className="mt-2 text-sm text-red-600">
            {error}
          </p>
        )}
      </div>

      <button type="submit" className="btn-primary w-full py-3" disabled={code.length !== CODE_LENGTH}>
        Verify and continue
        <Check className="h-4 w-4" aria-hidden="true" />
      </button>

      <div className="flex items-center justify-between text-sm">
        <button
          type="button"
          onClick={() => {
            setSentCode('')
            setSentAt(0)
            setError('')
          }}
          className="inline-flex items-center gap-1.5 font-medium text-slate-600 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Change number
        </button>
        <button
          type="button"
          onClick={() => {
            setSentCode(randomCode())
            setSentAt(Date.now())
            setCode('')
            setError('')
          }}
          className="font-medium text-bis-700 hover:text-bis-900"
        >
          Send a new code
        </button>
      </div>
    </form>
  )
}

function GoogleForm({ onDone }: { onDone: (email: string) => void }) {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!GMAIL_PATTERN.test(email.trim())) {
      setError('Enter a Gmail address, for example name@gmail.com.')
      return
    }
    onDone(email)
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <div>
        <label htmlFor="email" className="block text-sm font-medium text-slate-700">
          Gmail address
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          autoFocus
          placeholder="name@gmail.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={!!error}
          aria-describedby={error ? 'email-error' : undefined}
          className="mt-1.5 w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm text-slate-900 shadow-sm outline-none focus:border-bis-500 placeholder:text-slate-400"
        />
        {error && (
          <p id="email-error" role="alert" className="mt-2 text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
      <button type="submit" className="btn-primary w-full py-3">
        <Mail className="h-4 w-4" aria-hidden="true" />
        Continue with Gmail
      </button>
      <p className="text-xs leading-5 text-slate-500">
        This demo does not contact Google. The address is kept in this browser and used only for the
        name shown in the header.
      </p>
    </form>
  )
}

export default function Login() {
  const [tab, setTab] = useState<Tab>('phone')
  const { user, loading, signInWithPhone, signInWithGoogle, continueAsGuest } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  // Where to go after signing in: the page that sent us here, or the assistant.
  const next = (location.state as { from?: string } | null)?.from ?? '/assistant'

  // Someone who is already signed in has no reason to see this page.
  useEffect(() => {
    if (!loading && user) navigate(next, { replace: true })
  }, [loading, user, navigate, next])

  const go = () => navigate(next, { replace: true })

  return (
    <div className="min-h-dvh bg-gradient-to-b from-bis-50/70 to-white">
      <header className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5 rounded-lg">
          <Logo />
          <span className="text-base font-semibold tracking-tight text-slate-900">BIS Assistant</span>
        </Link>
        <StatusIndicator className="hidden sm:inline-flex" />
      </header>

      <main id="main" className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-6 sm:px-6 lg:grid-cols-2 lg:pt-12">
        <section className="hidden lg:block">
          <p className="inline-flex items-center gap-2 rounded-full border border-bis-200 bg-white px-3 py-1 text-xs font-semibold text-bis-700">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Sign in or try it as a guest
          </p>
          <h1 className="mt-6 text-4xl font-semibold leading-[1.15] tracking-tight text-slate-900">
            Answers from Indian Standards, <span className="text-bis-700">with the page they came from.</span>
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-slate-600">
            Ask in English, ಕನ್ನಡ or हिन्दी, by typing or by voice. Every supported answer names the BIS
            document and page it used.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-slate-700">
            {[
              'Guest mode has the same features as a signed-in account.',
              'Your session stays in this browser. Nothing is sent to a sign-in server.',
              'Sign out at any time from the header.',
            ].map((line) => (
              <li key={line} className="flex gap-2.5">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-bis-600" aria-hidden="true" />
                {line}
              </li>
            ))}
          </ul>
        </section>

        <section className="card mx-auto w-full max-w-md p-6 sm:p-8">
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Sign in</h2>
          <p className="mt-1.5 text-sm text-slate-600">Use your mobile number or a Gmail address.</p>

          <div role="tablist" aria-label="Sign-in method" className="mt-6 flex gap-1 rounded-xl bg-slate-100 p-1">
            <TabButton active={tab === 'phone'} onClick={() => setTab('phone')} icon={Phone} label="Phone" />
            <TabButton active={tab === 'google'} onClick={() => setTab('google')} icon={Mail} label="Gmail" />
          </div>

          <div className="mt-6">
            {tab === 'phone' ? (
              <PhoneForm
                onDone={(phone) => {
                  signInWithPhone(phone)
                  go()
                }}
              />
            ) : (
              <GoogleForm
                onDone={(email) => {
                  signInWithGoogle(email)
                  go()
                }}
              />
            )}
          </div>

          <div className="my-6 flex items-center gap-3">
            <span className="h-px flex-1 bg-slate-200" />
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">or</span>
            <span className="h-px flex-1 bg-slate-200" />
          </div>

          <button
            type="button"
            onClick={() => {
              continueAsGuest()
              go()
            }}
            className="btn-secondary w-full py-3"
          >
            <UserRound className="h-4 w-4" aria-hidden="true" />
            Continue as guest
          </button>
          <p className="mt-2 text-center text-xs text-slate-500">
            No account needed. Full access to the assistant.
          </p>
        </section>
      </main>
    </div>
  )
}
