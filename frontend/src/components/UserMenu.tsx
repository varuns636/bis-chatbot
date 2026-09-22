import { LogIn, LogOut, Mail, Phone, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../hooks/auth'

const METHOD_ICONS = { phone: Phone, google: Mail, guest: UserRound } as const
const METHOD_LABELS = { phone: 'Signed in with phone', google: 'Signed in with Gmail', guest: 'Guest session' } as const

/** The signed-in user's name with a sign-out menu, or a "Sign in" link when there is no session. */
export default function UserMenu({ className = '' }: { className?: string }) {
  const { user, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const container = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  if (!user) {
    return (
      <Link to="/login" state={{ from: location.pathname }} className={`btn-ghost ${className}`}>
        <LogIn className="h-4 w-4" aria-hidden="true" />
        Sign in
      </Link>
    )
  }

  const Icon = METHOD_ICONS[user.method]

  return (
    <div ref={container} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-medium text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-bis-50 text-bis-700">
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        <span className="max-w-[10rem] truncate">{user.name}</span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-64 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg"
        >
          <div className="px-3 py-2">
            <p className="truncate text-sm font-semibold text-slate-900">{user.name}</p>
            <p className="mt-0.5 text-xs text-slate-500">{METHOD_LABELS[user.method]}</p>
            {user.email && <p className="mt-1 truncate text-xs text-slate-500">{user.email}</p>}
          </div>
          <div className="my-1 h-px bg-slate-100" />
          {user.method === 'guest' && (
            <Link
              to="/login"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                signOut()
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-bis-700 hover:bg-bis-50"
            >
              <LogIn className="h-4 w-4" aria-hidden="true" />
              Sign in with phone or Gmail
            </Link>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              signOut()
              navigate('/login', { replace: true })
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
