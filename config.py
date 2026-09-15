"""Central configuration. Values come from environment variables or a local .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _path_from_env(name: str, default: str) -> Path:
    """Resolve a path setting. Relative paths are relative to the project root."""
    path = Path(os.getenv(name, default))
    return path if path.is_absolute() else BASE_DIR / path


def _number_from_env(name: str, default: int | float) -> int | float:
    """Read a numeric setting. The result has the same type as the default."""
    value = os.getenv(name)
    if not value:
        return default
    try:
        return type(default)(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a {type(default).__name__}, got {value!r}") from exc


RAW_DOCS_DIR = BASE_DIR / "data" / "raw"
CHROMA_DIR = _path_from_env("CHROMA_DIR", "data/chroma")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "bis_documents")
# Written by every index rebuild. Lists PDFs that were skipped (for example, scanned files).
INGESTION_REPORT = CHROMA_DIR / "ingestion_report.json"

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")

# Chunk size in characters. all-MiniLM-L6-v2 reads at most 256 tokens,
# so chunks stay near 800 characters to avoid silent truncation.
CHUNK_SIZE = _number_from_env("CHUNK_SIZE", 800)
CHUNK_OVERLAP = _number_from_env("CHUNK_OVERLAP", 120)

# Number of chunks returned by retrieval.
TOP_K = _number_from_env("TOP_K", 5)

# Local LLM. Ollama needs no API key.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT = _number_from_env("OLLAMA_TIMEOUT", 120.0)  # seconds
# Let the model reason before answering. Off by default because reasoning made answers take 1-3 minutes.
# "false" only works with hybrid or non-thinking models. The thinking-only qwen3:4b ignores it.
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false").strip().lower() in {"1", "true", "yes"}

# Sarvam AI (cloud). It receives voice recordings, and in the API also Kannada and Hindi questions and
# the English answer text to translate. English text questions and all search stay local.
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "").strip()
# Answer and question translation for Kannada and Hindi. See src/translation.py.
SARVAM_TRANSLATE_URL = os.getenv("SARVAM_TRANSLATE_URL", "https://api.sarvam.ai/translate")
SARVAM_TRANSLATE_MODEL = os.getenv("SARVAM_TRANSLATE_MODEL", "sarvam-translate:v1")
SARVAM_STT_URL = os.getenv("SARVAM_STT_URL", "https://api.sarvam.ai/speech-to-text")
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v4")  # see src/stt.py for how the defaults were tested
# "translate" returns English text from any supported Indian language, which matches the English
# document index. "transcribe" keeps the text in the spoken language.
SARVAM_STT_MODE = os.getenv("SARVAM_STT_MODE", "translate").strip().lower()
SARVAM_TIMEOUT = _number_from_env("SARVAM_TIMEOUT", 30.0)  # seconds

# FastAPI backend (src/api.py). Browser origins allowed by CORS: the Vite dev server by default.
API_CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("API_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]
MAX_AUDIO_BYTES = _number_from_env("MAX_AUDIO_BYTES", 10 * 1024 * 1024)

# Evidence gate (src/assistant.py). A question that does not name an indexed IS number is
# answered only when both limits are met. Calibrated on the sample index with 25 questions:
# relevant ones had top vector similarity 0.43-0.66, unrelated ones 0.14-0.47.
MIN_VECTOR_SCORE = _number_from_env("MIN_VECTOR_SCORE", 0.40)
# Share of the question's key terms that must appear in the retrieved passages.
MIN_KEYWORD_OVERLAP = _number_from_env("MIN_KEYWORD_OVERLAP", 0.5)
