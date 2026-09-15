import type { Language } from './api'

/** The only languages the backend accepts. Labels are shown in their own script. */
export const LANGUAGES: { value: Language; label: string; lang: string; name: string }[] = [
  { value: 'english', label: 'English', lang: 'en', name: 'English' },
  { value: 'kannada', label: 'ಕನ್ನಡ', lang: 'kn', name: 'Kannada' },
  { value: 'hindi', label: 'हिन्दी', lang: 'hi', name: 'Hindi' },
]

export function isLanguage(value: unknown): value is Language {
  return LANGUAGES.some((language) => language.value === value)
}

export function languageTag(value: Language): string {
  return LANGUAGES.find((language) => language.value === value)?.lang ?? 'en'
}
