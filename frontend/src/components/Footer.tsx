import { Link } from 'react-router'
import Logo from './Logo'

const TECHNOLOGIES = ['FastAPI', 'ChromaDB', 'BM25', 'Ollama', 'Sarvam AI', 'React', 'Tailwind CSS']

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-3">
        <div>
          <Link to="/" className="flex items-center gap-2.5">
            <Logo />
            <span className="font-semibold text-slate-900">BIS Assistant</span>
          </Link>
          <p className="mt-4 max-w-xs text-sm leading-6 text-slate-600">
            Evidence-based answers about Indian Standards and BIS services, with the PDF page behind every answer.
          </p>
        </div>

        <div>
          <h2 className="text-sm font-semibold text-slate-900">Built with</h2>
          <ul className="mt-4 flex flex-wrap gap-2">
            {TECHNOLOGIES.map((technology) => (
              <li key={technology} className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600">
                {technology}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h2 className="text-sm font-semibold text-slate-900">Disclaimer</h2>
          <p className="mt-4 text-sm leading-6 text-slate-600">
            For official decisions, always verify the latest information with BIS.
          </p>
          <p className="mt-2 text-xs leading-5 text-slate-500">
            BIS Assistant is a Smart India Hackathon prototype and is not an official BIS service.
          </p>
        </div>
      </div>
      <div className="border-t border-slate-100 py-5 text-center text-xs text-slate-500">
        © {new Date().getFullYear()} BIS Assistant · Smart India Hackathon prototype
      </div>
    </footer>
  )
}
