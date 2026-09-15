import { BadgeCheck, FileText, Search, Sparkles } from 'lucide-react'

/**
 * Illustration built from HTML, with no image files. The sample question, answer and cited page
 * (page 4 of is.14543.2004.pdf) match what the assistant returns for "What is IS 14543?".
 */
export default function HeroVisual() {
  return (
    <div className="relative mx-auto w-full max-w-md lg:max-w-none" aria-hidden="true">
      {/* Document */}
      <div className="card absolute -left-2 top-4 hidden w-60 -rotate-3 p-5 sm:block lg:-left-6">
        <div className="flex items-center gap-2 text-xs font-semibold text-bis-700">
          <FileText className="h-4 w-4" />
          IS 14543 : 2004
        </div>
        <p className="mt-2 text-sm font-semibold leading-snug text-slate-800">Packaged Drinking Water — Specification</p>
        <div className="mt-4 space-y-2">
          <div className="h-2 w-full rounded bg-slate-100" />
          <div className="h-2 w-11/12 rounded bg-slate-100" />
          <div className="h-2 w-full rounded bg-bis-100" />
          <div className="h-2 w-4/5 rounded bg-bis-100" />
          <div className="h-2 w-10/12 rounded bg-slate-100" />
          <div className="h-2 w-3/5 rounded bg-slate-100" />
        </div>
        <p className="mt-4 text-[11px] font-medium text-slate-400">Page 4</p>
      </div>

      {/* Chat */}
      <div className="card relative ml-auto w-full p-5 shadow-xl shadow-bis-900/5 sm:mt-16 sm:w-[22rem] lg:mr-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-bis-50 text-bis-700">
              <Sparkles className="h-4 w-4" />
            </span>
            BIS Assistant
          </div>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">English · ಕನ್ನಡ · हिन्दी</span>
        </div>

        <div className="mt-5 flex justify-end">
          <p className="max-w-[80%] rounded-2xl rounded-br-md bg-bis-700 px-3.5 py-2 text-sm text-white">What is IS 14543?</p>
        </div>

        <div className="mt-3 rounded-2xl rounded-bl-md border border-slate-200 bg-slate-50 px-3.5 py-3">
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
            <BadgeCheck className="h-3.5 w-3.5" />
            Evidence found
          </span>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            IS 14543:2004 is the specification for packaged drinking water (other than packaged natural mineral water).
          </p>
          <span className="mt-2 inline-flex items-center gap-1 rounded-md border border-bis-200 bg-white px-1.5 py-0.5 text-[11px] font-medium text-bis-800">
            <FileText className="h-3 w-3" />
            is.14543.2004.pdf · p. 4
          </span>
        </div>
      </div>

      {/* Search chip */}
      <div className="card absolute -bottom-6 left-4 flex animate-float items-center gap-2.5 px-3.5 py-2.5 sm:left-10">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-bis-700 text-white">
          <Search className="h-4 w-4" />
        </span>
        <div>
          <p className="text-xs font-semibold text-slate-900">Hybrid search</p>
          <p className="text-[11px] text-slate-500">Vector + BM25 keyword match</p>
        </div>
      </div>
    </div>
  )
}
