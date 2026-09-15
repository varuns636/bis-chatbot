import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { getHealth, getStatus, type StatusResponse } from '../lib/api'

export type ConnectionState = 'checking' | 'connected' | 'unavailable'

interface BackendStatus {
  state: ConnectionState
  /** Details from /api/status, when the backend answered it. */
  status: StatusResponse | null
  refresh: () => void
}

const BackendStatusContext = createContext<BackendStatus>({ state: 'checking', status: null, refresh: () => {} })

const POLL_MS = 15_000

/** Polls /api/health (and /api/status for details) so every page can show the connection state. */
export function BackendStatusProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConnectionState>('checking')
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [refreshCount, setRefreshCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        await getHealth()
      } catch {
        if (!cancelled) setState('unavailable')
        return
      }
      if (cancelled) return
      setState('connected')
      try {
        const details = await getStatus()
        if (!cancelled) setStatus(details)
      } catch {
        // Details are optional; the connection itself is fine.
      }
    }
    void check()
    const timer = window.setInterval(check, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [refreshCount])

  const refresh = useCallback(() => {
    setState('checking')
    setRefreshCount((count) => count + 1)
  }, [])

  return <BackendStatusContext.Provider value={{ state, status, refresh }}>{children}</BackendStatusContext.Provider>
}

export function useBackendStatus(): BackendStatus {
  return useContext(BackendStatusContext)
}
