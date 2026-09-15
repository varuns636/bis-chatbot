import { useBackendStatus, type ConnectionState } from '../hooks/backendStatus'

const APPEARANCE: Record<ConnectionState, { dot: string; label: string }> = {
  checking: { dot: 'bg-slate-400 animate-pulse', label: 'Checking connection' },
  connected: { dot: 'bg-emerald-500', label: 'Backend connected' },
  unavailable: { dot: 'bg-rose-500', label: 'Backend unavailable' },
}

/** `className` sets the display (for example "hidden sm:inline-flex"), so the base classes leave it out. */
export default function StatusIndicator({ className = 'inline-flex' }: { className?: string }) {
  const { state, status } = useBackendStatus()
  const { dot, label } = APPEARANCE[state]
  const detail = state === 'connected' && status ? `Model: ${status.llm.model}, ${status.index.chunks} indexed passages` : undefined

  return (
    <span
      role="status"
      aria-live="polite"
      title={detail}
      className={`items-center gap-2 whitespace-nowrap rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 ${className}`}
    >
      <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} aria-hidden="true" />
      {label}
    </span>
  )
}
