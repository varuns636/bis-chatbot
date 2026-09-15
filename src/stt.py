"""Speech-to-text through the Sarvam AI API.

Voice questions are the only data this app sends to a cloud service. The audio goes to Sarvam,
text comes back, and from there the question follows the normal local pipeline.

Defaults, checked against the live API in September 2026 (saaras:v4, two runs per test clip):
- mode "translate": Hindi questions came back as clean English, which matches the English
  document index.
- No keyterms. Sarvam accepts a list of expected terms, but when given the indexed IS numbers
  it inserted "BIS IS 14543" into a Hindi question that never mentioned it. That would limit
  search to one standard. Without keyterms the translations were exact.
- A spoken "What is IS 14543?" came back as "What is this 14,543?". normalize_transcript()
  repairs number formats like this before search.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

import requests

import config
from src.languages import to_ascii_digits
from src.retrieval import IS_NUMBER_PATTERN

LANGUAGE_NAMES = {
    "en-IN": "English", "hi-IN": "Hindi", "bn-IN": "Bengali", "kn-IN": "Kannada", "ml-IN": "Malayalam",
    "mr-IN": "Marathi", "od-IN": "Odia", "pa-IN": "Punjabi", "ta-IN": "Tamil", "te-IN": "Telugu",
    "gu-IN": "Gujarati", "as-IN": "Assamese", "ur-IN": "Urdu", "ne-IN": "Nepali", "kok-IN": "Konkani",
    "ks-IN": "Kashmiri", "sd-IN": "Sindhi", "sa-IN": "Sanskrit", "sat-IN": "Santali", "mni-IN": "Manipuri",
    "brx-IN": "Bodo", "mai-IN": "Maithili", "doi-IN": "Dogri",
}

# "14,543" -> "14543", also when a letter touches the number ("S14,543").
GROUPED_NUMBER = re.compile(r"(?<!\d)\d{1,3}(?:,\d{3})+(?!\d)")
# "S14543", "S 14543", "I.S. 14543", "I S 14543" -> "IS 14543". Capital letters only, to leave words like "is" alone.
MISHEARD_IS = re.compile(r"(?<![A-Za-z])(?:I\.?\s?S\.?|S)\s*[:\-]?\s*(\d{2,5})\b")
NUMBER = re.compile(r"\b\d+\b")


class STTError(RuntimeError):
    """Speech could not be turned into text. The message is safe to show users; it never contains the key."""


@dataclass
class Transcript:
    text: str  # cleaned text, used as the question
    raw_text: str  # exactly what the API returned
    language_code: str | None  # spoken language reported by Sarvam, e.g. "hi-IN"
    language_probability: float | None = None

    @property
    def language_name(self) -> str:
        return LANGUAGE_NAMES.get(self.language_code or "", self.language_code or "unknown language")


def indexed_is_numbers(titles: Iterable[str]) -> set[str]:
    """IS numbers of the indexed standards, from their titles."""
    return {number for title in titles for number in IS_NUMBER_PATTERN.findall(title)}


def normalize_transcript(text: str, known_numbers: Iterable[str] = ()) -> str:
    """Repair number formats that break IS-number search.

    1. Turn Kannada and Devanagari digits into ASCII digits.
    2. Remove thousands separators: "14,543" -> "14543".
    3. Fix misheard prefixes: "S14543" or "I.S. 14543" -> "IS 14543".
    4. Put "IS" before a bare number that matches an indexed standard: "this 14543" -> "this IS 14543".
       Only indexed numbers are changed, so "the limit is 250 mg" stays as it is.
    """
    text = to_ascii_digits(text)
    text = GROUPED_NUMBER.sub(lambda m: m.group().replace(",", ""), text)
    text = MISHEARD_IS.sub(lambda m: f"IS {m.group(1)}", text)
    known = set(known_numbers)
    named = {m.start(1) for m in IS_NUMBER_PATTERN.finditer(text)}
    return NUMBER.sub(lambda m: f"IS {m.group()}" if m.group() in known and m.start() not in named else m.group(), text)


def _error_message(response: requests.Response) -> str:
    if response.status_code in (401, 403):
        return "The Sarvam API key was rejected. Check SARVAM_API_KEY in .env."
    if response.status_code == 429:
        return "The Sarvam rate or credit limit was reached. Wait a moment and try again."
    try:
        detail = response.json().get("error", {}).get("message", "")
    except ValueError:
        detail = ""
    return f"Sarvam speech-to-text failed (HTTP {response.status_code})" + (f": {detail}" if detail else ".")


def transcribe(
    audio: bytes,
    filename: str = "question.wav",
    known_numbers: Iterable[str] = (),
    language_code: str = "unknown",
    mode: str | None = None,
    content_type: str = "audio/wav",
) -> Transcript:
    """Send a recording to Sarvam and return the cleaned transcript. Raises STTError on any failure.

    `language_code` is "unknown" (auto-detect) or a code such as "kn-IN". `mode` defaults to SARVAM_STT_MODE.
    """
    if not config.SARVAM_API_KEY:
        raise STTError("Voice input needs a Sarvam API key. Add SARVAM_API_KEY to .env and restart the app.")
    if not audio:
        raise STTError("The recording is empty. Please record your question again.")

    try:
        response = requests.post(
            config.SARVAM_STT_URL,
            headers={"api-subscription-key": config.SARVAM_API_KEY},
            files={"file": (filename, audio, content_type)},
            data={"model": config.SARVAM_STT_MODEL, "mode": mode or config.SARVAM_STT_MODE, "language_code": language_code},
            timeout=config.SARVAM_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise STTError(f"Cannot reach the Sarvam speech service ({type(exc).__name__}). Check the internet connection.") from exc

    if response.status_code != 200:
        raise STTError(_error_message(response))
    try:
        body = response.json()
    except ValueError as exc:
        raise STTError("Sarvam returned an unreadable response. Please try again.") from exc
    raw_text = (body.get("transcript") or "").strip()
    if not raw_text:
        raise STTError("No speech was detected in the recording. Please try again.")
    return Transcript(
        text=normalize_transcript(raw_text, known_numbers),
        raw_text=raw_text,
        language_code=body.get("language_code"),
        language_probability=body.get("language_probability"),
    )
