import { Link } from 'react-router'
import Navbar from '../components/Navbar'

export default function NotFound() {
  return (
    <div className="min-h-dvh bg-white">
      <Navbar />
      <main id="main" className="mx-auto flex max-w-xl flex-col items-center px-4 py-32 text-center">
        <p className="text-sm font-semibold text-bis-600">404</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">Page not found</h1>
        <p className="mt-3 text-slate-600">The page you are looking for does not exist.</p>
        <div className="mt-8 flex gap-3">
          <Link to="/" className="btn-secondary">Go home</Link>
          <Link to="/assistant" className="btn-primary">Open the assistant</Link>
        </div>
      </main>
    </div>
  )
}
