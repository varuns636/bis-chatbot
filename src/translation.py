"""Translation for Kannada and Hindi answers and questions.

Answers are always generated in English by the local LLM, from English evidence. For Kannada and
Hindi, only the natural-language text of the answer is then translated with Sarvam. Anything that
must stay exact is kept away from the translator:

- Citations such as [Source: is.14543.2004.pdf, page 5] are removed from each line before
  translation and put back, unchanged, at the end of that line.
- URLs, file names, IS references, numbers with units, clause numbers and technical abbreviations
  are replaced with placeholders (__P0__, __P1__, ...), then restored. In a live test (September
  2026), Sarvam left these placeholders intact. Without them it wrote "IS 14543" as "ಐ.ಎಸ್. 14543"
  and "HCl" as "ಎಚ್.ಸಿ.ಎಲ್.", translated the citation labels and (with mayura:v1) changed ".pdf"
  to "पीडीएफ".
- Each translated line is checked: every placeholder must come back exactly once, the numbers
  must match the English line, the length must be plausible and the text must be in the target
  script. A line that fails keeps its English text, and the answer gets a warning.

If the translation service fails, the English answer is returned with a warning.

Typed Kannada or Hindi questions are translated to English the same way before search. If Sarvam
is unavailable or its translation looks wrong, the local LLM translates the question instead.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

import requests

import config
from src.assistant import CITATION_PATTERN, extract_citations
from src.languages import SUPPORTED_LANGUAGES, Language, to_ascii_digits
from src.llm import LLMProvider

MAX_INPUT_CHARS = 2000  # sarvam-translate:v1 limit per request
MAX_PARALLEL_REQUESTS = 4

# Terms kept away from the translator. Order matters: URLs, file names, IS references,
# numbers with an optional unit, then technical abbreviations.
PROTECTED = re.compile(
    r"https?://\S+"
    r"|[\w.-]+\.pdf\b"
    r"|\bIS\s*:?\s*\d+(?:\s*[-:]\s*\d+)*(?:\s*\(\s*Part\s*\d+\s*\))?(?:\s*[:(]\s*\d{4}\s*\)?)?"
    r"|\d+(?:[.,:]\d+)*(?:\s?(?:°\s?[CF]|%|mg/[lL]|µg/[lL]|mm²|ml|mm|cm|km|kV|kW|kg|ppm|Ω|[VAWgm])(?![A-Za-z]))?"
    r"|\bE\.\s?coli\b|\bpH\b"
    r"|\b(?:[A-Z]{2,}[a-z]?|[A-Z][a-z][A-Z][A-Za-z]*)\b"
)
PLACEHOLDER = re.compile(r"__P(\d+)__")
LINE_PREFIX = re.compile(r"^\s*(?:(?:[-*•]|\d+[.)])\s+)?")  # indentation and a list marker such as "- " or "1. "
SCRIPTS = {
    "en-IN": re.compile(r"[A-Za-z]"),
    "kn-IN": re.compile(r"[ಀ-೿]"),
    "hi-IN": re.compile(r"[ऀ-ॿ]"),
}
LETTER = re.compile(r"[^\W\d_]")

TRANSLATION_PROMPT = (
    "You are a translator for a BIS (Bureau of Indian Standards) assistant. Translate the user's text into "
    "{target}. Keep IS numbers, clause numbers, file names, page numbers, units, numeric values and any "
    "[Source: ...] citations exactly as they are. Reply with the translation only, with no notes."
)


class TranslationError(RuntimeError):
    """Translation failed. The message is safe to show users; it never contains the key."""


class TranslationProvider(Protocol):
    name: str
    model: str

    def translate(self, text: str, source_code: str, target_code: str) -> str:
        """Translate plain text between language codes such as "en-IN" and "kn-IN"."""


class SarvamTranslator:
    """Sarvam text translation (POST /translate)."""

    name = "sarvam"

    def __init__(self, api_key: str, url: str, model: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.url = url
        self.model = model
        self.timeout = timeout

    def translate(self, text: str, source_code: str, target_code: str) -> str:
        try:
            response = requests.post(
                self.url,
                headers={"api-subscription-key": self.api_key},
                json={
                    "input": text,
                    "source_language_code": source_code,
                    "target_language_code": target_code,
                    "model": self.model,
                    "numerals_format": "international",  # keep 0-9 digits
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise TranslationError(f"Cannot reach the Sarvam translation service ({type(exc).__name__}).") from exc
        if response.status_code != 200:
            raise TranslationError(_error_message(response))
        try:
            translated = (response.json().get("translated_text") or "").strip()
        except ValueError as exc:
            raise TranslationError("Sarvam returned an unreadable translation response.") from exc
        if not translated:
            raise TranslationError("Sarvam returned an empty translation.")
        return translated


def _error_message(response: requests.Response) -> str:
    if response.status_code in (401, 403):
        return "The Sarvam API key was rejected."
    if response.status_code == 429:
        return "The Sarvam rate or credit limit was reached."
    try:
        body = response.json()
        error = body.get("error", body)
        detail = error.get("message", "") if isinstance(error, dict) else ""
    except ValueError:
        detail = ""
    return f"Sarvam translation failed (HTTP {response.status_code})" + (f": {detail}" if detail else ".")


def get_translator() -> TranslationProvider | None:
    """The Sarvam translator, or None when SARVAM_API_KEY is not set."""
    if not config.SARVAM_API_KEY:
        return None
    return SarvamTranslator(
        config.SARVAM_API_KEY, config.SARVAM_TRANSLATE_URL, config.SARVAM_TRANSLATE_MODEL, config.SARVAM_TIMEOUT
    )


def mask(text: str) -> tuple[str, list[str]]:
    """Replace protected terms with __P0__, __P1__, ... Returns the masked text and the terms in order."""
    tokens: list[str] = []

    def placeholder(match: re.Match) -> str:
        tokens.append(match.group())
        return f"__P{len(tokens) - 1}__"

    return PROTECTED.sub(placeholder, text), tokens


def unmask(text: str, tokens: list[str]) -> str | None:
    """Put protected terms back. Returns None if a placeholder is missing, repeated or unknown."""
    found = sorted(int(number) for number in PLACEHOLDER.findall(text))
    if found != list(range(len(tokens))):
        return None
    return PLACEHOLDER.sub(lambda m: tokens[int(m.group(1))], text)


def is_plausible(source: str, translated: str, target_code: str) -> bool:
    """Check a translated line against its source: same numbers, sensible length, target script."""
    if sorted(re.findall(r"\d+", source)) != sorted(re.findall(r"\d+", to_ascii_digits(translated))):
        return False
    if not 0.3 <= len(translated) / max(len(source), 1) <= 4:
        return False
    return bool(SCRIPTS[target_code].search(PROTECTED.sub("", translated)))


@dataclass
class LineResult:
    text: str
    status: str  # "translated", "kept" (translation looked wrong) or "skipped" (nothing to translate)


def translate_line(line: str, source_code: str, target_code: str, translator: TranslationProvider) -> LineResult:
    """Translate one line. Citations and protected terms come back unchanged. Raises TranslationError."""
    citations = [match.group() for match in CITATION_PATTERN.finditer(line)]
    body = CITATION_PATTERN.sub("", line)
    prefix = LINE_PREFIX.match(body).group()
    content = re.sub(r"\s+([.,;:!?।])", r"\1", body[len(prefix):])
    content = re.sub(r"\s{2,}", " ", content).strip()
    if len(LETTER.findall(PROTECTED.sub("", content))) < 2:
        return LineResult(line, "skipped")

    masked, tokens = mask(content)
    if len(masked) > MAX_INPUT_CHARS:
        return LineResult(line, "kept")
    restored = unmask(translator.translate(masked, source_code, target_code), tokens)
    if restored is None or not is_plausible(content, restored, target_code):
        return LineResult(line, "kept")
    return LineResult(prefix + restored.strip() + "".join(f" {c}" for c in citations), "translated")


@dataclass
class TranslatedText:
    text: str
    translated: int  # lines translated
    kept: int  # lines kept in the source language because their translation looked wrong


def translate_text(text: str, target_code: str, translator: TranslationProvider, source_code: str = "en-IN") -> TranslatedText:
    """Translate line by line, several lines in parallel. Raises TranslationError if the service fails."""
    lines = text.split("\n")
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS) as pool:
        results = list(pool.map(lambda line: translate_line(line, source_code, target_code, translator), lines))
    return TranslatedText(
        "\n".join(r.text for r in results),
        sum(r.status == "translated" for r in results),
        sum(r.status == "kept" for r in results),
    )


def localize_answer(
    english: str, language: Language, translator: TranslationProvider | None
) -> tuple[str, list[str], bool]:
    """Return the answer in the chosen language, warnings, and whether any text was translated.

    English passes through untouched. For Kannada and Hindi, any failure returns the English answer
    with a warning instead of failing the request.
    """
    if language == "english":
        return english, [], False
    name = language.title()
    if translator is None:
        return english, [f"Translation to {name} is not configured (SARVAM_API_KEY is missing). The answer is shown in English."], False
    try:
        result = translate_text(english, SUPPORTED_LANGUAGES[language], translator)
    except TranslationError as exc:
        return english, [f"Translation to {name} failed: {exc} The answer is shown in English."], False
    if extract_citations(result.text) != extract_citations(english):
        return english, [f"Translation to {name} changed the citations, so the answer is shown in English."], False
    warnings = []
    if result.kept:
        warnings.append(
            f"{result.kept} of {result.kept + result.translated} lines are shown in English, because their "
            f"{name} translation changed a number, IS reference or technical term."
        )
    return result.text, warnings, result.translated > 0


def translate(llm: LLMProvider, text: str, target: Language) -> str:
    """Translate text with the local LLM. Used only when Sarvam cannot translate a question."""
    messages = [
        {"role": "system", "content": TRANSLATION_PROMPT.format(target=target.title())},
        {"role": "user", "content": text},
    ]
    return "".join(llm.stream_chat(messages)).strip()


def question_to_english(
    question: str, translator: TranslationProvider | None, llm: LLMProvider
) -> tuple[str, list[str]]:
    """Translate a Kannada or Hindi question to English for search. Returns the text and any warnings.

    Sarvam is tried first. If it is not configured, fails, or its translation looks wrong, the local
    LLM translates the question. Raises LLMUnavailableError if that fallback is needed and Ollama is down.
    """
    if translator is None:
        return translate(llm, question, "english"), []
    source = "kn-IN" if SCRIPTS["kn-IN"].search(question) else "hi-IN"
    try:
        result = translate_line(question, source, "en-IN", translator)
        if result.status == "translated":
            return result.text, []
        warning = "Sarvam's translation of the question looked wrong, so the local LLM translated it."
    except TranslationError as exc:
        warning = f"Sarvam could not translate the question ({exc}), so the local LLM translated it."
    return translate(llm, question, "english"), [warning]
