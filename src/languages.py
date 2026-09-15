"""Languages the BIS assistant API supports for answers and voice input.

The API accepts exactly these three. Sarvam supports more languages, but they are not exposed.
"""

import re
from typing import Literal

SUPPORTED_LANGUAGES = {
    "english": "en-IN",
    "kannada": "kn-IN",
    "hindi": "hi-IN",
}
Language = Literal["english", "kannada", "hindi"]

# Kannada and Devanagari digits -> ASCII digits, so spoken or typed IS numbers match the index.
NATIVE_DIGITS = str.maketrans("೦೧೨೩೪೫೬೭೮೯०१२३४५६७८९", "01234567890123456789")
# Kannada (U+0C80-U+0CFF) or Devanagari (U+0900-U+097F) letters.
INDIC_SCRIPT = re.compile(r"[ऀ-ॿಀ-೿]")


def to_ascii_digits(text: str) -> str:
    return text.translate(NATIVE_DIGITS)


def needs_translation(text: str) -> bool:
    """True if the text is written in Kannada or Hindi script and must be translated before an English search."""
    return bool(INDIC_SCRIPT.search(text))
