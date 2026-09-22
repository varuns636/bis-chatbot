import { type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useAuth } from '../hooks/auth'

/**
 * Sends visitors without a session to /login, remembering the page they wanted.
 *
 * A guest session counts: guest mode is a normal session with the same access.
 */
export default function RequireSession({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  // The stored session has not been read yet. Rendering nothing avoids a flash of the login page.
  if (loading) return null
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <>{children}</>
}
