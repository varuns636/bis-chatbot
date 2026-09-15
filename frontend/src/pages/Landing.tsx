import {
  ArrowRight,
  BadgeCheck,
  BookOpenText,
  Cpu,
  Database,
  FileSearch,
  FileText,
  Languages,
  Layers,
  MessageSquareText,
  Mic,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  TextSearch,
  Waves,
} from 'lucide-react'
import { useEffect } from 'react'
import { Link, useLocation } from 'react-router'
import Footer from '../components/Footer'
import HeroVisual from '../components/HeroVisual'
import Navbar from '../components/Navbar'

const FEATURES = [
  {
    icon: FileSearch,
    title: 'Indian Standards Search',
    text: 'Find indexed Indian Standards by product, topic, clause or exact IS number, such as IS 14543.',
  },
  {
    icon: ShieldCheck,
    title: 'Evidence-Based Answers',
    text: 'Answers come only from retrieved BIS text. When the evidence is weak, the assistant says so instead of guessing.',
  },
  {
    icon: Languages,
    title: 'English, Kannada, and Hindi',
    text: 'Read answers in English, ಕನ್ನಡ or हिन्दी. IS numbers, values and citations stay exactly as in the source.',
  },
  {
    icon: Mic,
    title: 'Voice Questions',
    text: 'Speak your question. Sarvam AI turns the speech into text, and the same evidence checks run.',
  },
  {
    icon: Cpu,
    title: 'Local AI with Ollama',
    text: 'Answers are written by a language model that runs locally through Ollama, next to your document index.',
  },
  {
    icon: FileText,
    title: 'Source Citations and PDF Pages',
    text: 'Every supported answer names the PDF file and page number, with a preview of the passage it used.',
  },
]

const STEPS = [
  { icon: MessageSquareText, title: 'Ask a question', text: 'Type or speak in English, Kannada or Hindi.' },
  {
    icon: ScanSearch,
    title: 'Search BIS documents',
    text: 'Hybrid search combines meaning-based search with keyword search, so exact IS and clause numbers are found.',
  },
  {
    icon: BadgeCheck,
    title: 'Verify evidence',
    text: 'The assistant checks that the passages match your question. If they do not, it tells you instead of answering.',
  },
  {
    icon: Sparkles,
    title: 'Generate a cited answer',
    text: 'The local model answers only from the evidence and cites the file and page for each point.',
  },
]

const TECHNOLOGY = [
  { icon: BookOpenText, title: 'BIS documents', text: 'Indian Standards and the BIS Act, split into passages page by page.' },
  { icon: Layers, title: 'Hybrid search', text: 'Vector and keyword results merged with Reciprocal Rank Fusion.' },
  { icon: Database, title: 'ChromaDB', text: 'Stores passage embeddings from all-MiniLM-L6-v2 for meaning-based search.' },
  { icon: TextSearch, title: 'BM25', text: 'Keyword ranking that catches exact IS numbers and clause numbers.' },
  { icon: Cpu, title: 'Ollama', text: 'Runs the answer model locally. No paid LLM API is used.' },
  { icon: Waves, title: 'Sarvam AI', text: 'Speech-to-text for voice questions and Kannada and Hindi translation.' },
]

function SectionHeading({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="text-sm font-semibold uppercase tracking-wider text-bis-600">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">{title}</h2>
      <p className="mt-4 text-base leading-7 text-slate-600">{text}</p>
    </div>
  )
}

export default function Landing() {
  const { hash } = useLocation()

  // Scroll to #features or #how-it-works when arriving from another page.
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView()
    else window.scrollTo(0, 0)
  }, [hash])

  return (
    <div className="min-h-dvh bg-white">
      <Navbar />
      <main id="main">
        {/* Hero */}
        <section className="relative overflow-hidden border-b border-slate-100 bg-gradient-to-b from-bis-50/70 to-white">
          <div className="mx-auto grid max-w-6xl items-center gap-16 px-4 pb-24 pt-16 sm:px-6 lg:grid-cols-2 lg:pt-24">
            <div className="animate-fade-up">
              <p className="inline-flex items-center gap-2 rounded-full border border-bis-200 bg-white px-3 py-1 text-xs font-semibold text-bis-700">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Evidence-based · Cited · Multilingual
              </p>
              <h1 className="mt-6 text-4xl font-semibold leading-[1.1] tracking-tight text-slate-900 sm:text-5xl lg:text-[3.4rem]">
                Understand Indian Standards. <span className="text-bis-700">Get Clear Answers.</span>
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-8 text-slate-600">
                BIS Assistant helps industries and consumers understand Indian Standards, certification-related
                information, product requirements and BIS services. Every answer is based on evidence from BIS
                documents and shows the PDF page it came from.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/assistant" className="btn-primary px-5 py-3 text-base">
                  Start Asking
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
                <Link to="/#how-it-works" className="btn-secondary px-5 py-3 text-base">
                  How It Works
                </Link>
              </div>
            </div>
            <HeroVisual />
          </div>
        </section>

        {/* Features */}
        <section id="features" className="scroll-mt-20 py-24">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <SectionHeading
              eyebrow="Features"
              title="Everything you need to read a standard with confidence"
              text="Built for manufacturers, testing labs, students and consumers who need clear answers backed by the source text."
            />
            <ul className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map(({ icon: Icon, title, text }) => (
                <li key={title} className="card group p-6 transition hover:-translate-y-0.5 hover:shadow-md">
                  <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-bis-50 text-bis-700 transition-colors group-hover:bg-bis-700 group-hover:text-white">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <h3 className="mt-5 text-base font-semibold text-slate-900">{title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="scroll-mt-20 border-y border-slate-100 bg-slate-50 py-24">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <SectionHeading
              eyebrow="How it works"
              title="From question to cited answer in four steps"
              text="The assistant never answers from memory. It searches the documents first and answers only when the evidence supports it."
            />
            <ol className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
              {STEPS.map(({ icon: Icon, title, text }, index) => (
                <li key={title} className="card relative p-6">
                  <span className="text-xs font-semibold text-bis-600">Step {index + 1}</span>
                  <span className="mt-3 flex h-11 w-11 items-center justify-center rounded-xl bg-bis-700 text-white">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <h3 className="mt-5 text-base font-semibold text-slate-900">{title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Technology */}
        <section id="technology" className="py-24">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <SectionHeading
              eyebrow="Technology"
              title="Transparent by design"
              text="Documents, search and answer generation run on your machine. Only voice recordings and Kannada or Hindi translation use the Sarvam AI cloud service."
            />
            <ul className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {TECHNOLOGY.map(({ icon: Icon, title, text }) => (
                <li key={title} className="flex gap-4 rounded-2xl border border-slate-200 p-5">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
                    <p className="mt-1 text-sm leading-6 text-slate-600">{text}</p>
                  </div>
                </li>
              ))}
            </ul>

            <div className="mt-16 flex flex-col items-center justify-between gap-6 rounded-3xl bg-bis-800 px-8 py-10 text-center sm:flex-row sm:text-left">
              <div>
                <h2 className="text-2xl font-semibold text-white">Ask your first question</h2>
                <p className="mt-2 text-sm text-bis-100">Try “What is IS 14543?” in English, ಕನ್ನಡ or हिन्दी.</p>
              </div>
              <Link to="/assistant" className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-bis-800 shadow-sm transition-colors hover:bg-bis-50">
                Start Assistant
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  )
}
