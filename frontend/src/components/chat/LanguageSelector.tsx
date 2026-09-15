import type { Language } from '../../lib/api'
import { LANGUAGES } from '../../lib/languages'

interface Props {
  value: Language
  onChange: (language: Language) => void
  disabled?: boolean
}

/** Segmented control built from native radio buttons, so arrow keys and screen readers work. */
export default function LanguageSelector({ value, onChange, disabled = false }: Props) {
  return (
    <fieldset className="flex shrink-0" disabled={disabled}>
      <legend className="sr-only">Answer language</legend>
      <div className="inline-flex rounded-xl border border-slate-200 bg-slate-100 p-1">
        {LANGUAGES.map((language) => (
          <label key={language.value} className="relative">
            <input
              type="radio"
              name="answer-language"
              value={language.value}
              checked={value === language.value}
              onChange={() => onChange(language.value)}
              className="peer sr-only"
            />
            <span
              lang={language.lang}
              className="block cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors peer-checked:bg-white peer-checked:text-bis-800 peer-checked:shadow-sm peer-focus-visible:outline-2 peer-focus-visible:outline-bis-600 peer-disabled:cursor-not-allowed peer-disabled:opacity-60 hover:text-slate-900"
            >
              {language.label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
