"""FastAPI backend for the BIS assistant.

It reuses the Streamlit app's pipeline: hybrid retrieval (ChromaDB + BM25), the evidence gate,
the local Ollama LLM, citation checks and Sarvam speech-to-text.

Run from the project root:  uvicorn src.api:app --reload --port 8000
Interactive docs:           http://127.0.0.1:8000/docs

Languages. `language` is english, kannada or hindi (anything else returns HTTP 422). It sets
the answer language. Search and answer generation always run in English, because the documents
are English and the local LLM writes English reliably:
- A question typed in Kannada or Hindi script is translated to English with Sarvam (or the local
  LLM if Sarvam fails).
- Voice: Sarvam transcribes the audio in the selected language (the transcript shown to the
  user). For Kannada and Hindi, a second Sarvam call in "translate" mode gives the English text
  used for search. The two calls run in parallel.
- Kannada and Hindi answers: the grounded English answer is checked, then only its text is
  translated with Sarvam. Citations, IS numbers and values stay unchanged (see src/translation.py).
  If translation fails, the English answer is returned with a warning.

Streaming. POST /api/chat/stream returns the same answer as /api/chat as newline-delimited JSON
events, sending English answer text as the LLM writes it.
"""

import json
import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_chroma import Chroma
from pydantic import BaseModel, Field, field_validator

import config
from src.assistant import (
    check_citations,
    check_evidence,
    generate_answer,
    indexed_standards,
    standard_label,
    unsupported_standard_numbers,
)
from src.languages import SUPPORTED_LANGUAGES, Language, needs_translation, to_ascii_digits
from src.llm import LLMProvider, LLMUnavailableError, get_llm
from src.retrieval import BM25Index, SearchResult, build_bm25_index, load_indexed_chunks, load_unavailable_files, open_vector_store
from src.stt import STTError, Transcript, indexed_is_numbers, transcribe
from src.translation import TranslationProvider, get_translator, localize_answer, question_to_english

logger = logging.getLogger(__name__)


@dataclass
class SearchIndex:
    store: Chroma
    bm25: BM25Index
    unavailable_files: dict[str, str]
    titles: list[str]


@lru_cache(maxsize=1)
def get_search_index() -> SearchIndex:
    """Load Chroma and BM25 once per process. Restart the API after rebuilding the index."""
    store = open_vector_store(config.CHROMA_DIR, config.CHROMA_COLLECTION)
    bm25 = build_bm25_index(load_indexed_chunks(store))
    return SearchIndex(store, bm25, load_unavailable_files(config.INGESTION_REPORT), indexed_standards(bm25.chunks))


def get_llm_provider() -> LLMProvider:
    return get_llm()


def get_translation_provider() -> TranslationProvider | None:
    return get_translator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the index (and the embedding model) at startup instead of on the first request.
    app.dependency_overrides.get(get_search_index, get_search_index)()
    yield


app = FastAPI(title="BIS Assistant API", version="1.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.API_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------- Request and response models ----------


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    language: Language = Field(default="english", description="Answer language: english, kannada or hindi.")
    history: list[str] = Field(default_factory=list, max_length=20, description="Earlier user questions, oldest first.")

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("language", mode="before")
    @classmethod
    def lowercase_language(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class Citation(BaseModel):
    source: str
    page: int
    standard: str
    title: str
    preview: str


class ChatResponse(BaseModel):
    answer: str
    language: Language
    citations: list[Citation]
    evidence_found: bool
    model: str
    search_query: str
    warnings: list[str]
    english_answer: str | None = Field(None, description="The grounded English answer, for Kannada and Hindi requests.")
    translated: bool = Field(False, description="True if the answer text was translated from English.")


class SpeechToTextResponse(BaseModel):
    transcript: str
    language: Language
    language_code: str
    provider: str


class VoiceChatResponse(BaseModel):
    transcript: str
    answer: str
    language: Language
    citations: list[Citation]
    evidence_found: bool
    stt_provider: str
    llm_provider: str
    model: str
    search_query: str
    warnings: list[str]
    english_answer: str | None = None
    translated: bool = False


# ---------- Pipeline ----------


def to_citation(result: SearchResult) -> Citation:
    return Citation(
        source=result.source,
        page=result.page,
        standard=standard_label(result.title, result.source),
        title=result.title,
        preview=" ".join(result.text.split())[:200],
    )


def iter_answer(
    question: str,
    language: Language,
    history: list[str],
    index: SearchIndex,
    llm: LLMProvider,
    translator: TranslationProvider | None,
    search_query: str | None = None,
) -> Iterator[tuple[str, object]]:
    """Search, check the evidence, answer in English and translate the answer if needed.

    Yields ("token", text) while an English answer is being written, then ("result", dict).
    Kannada and Hindi answers yield no tokens: they are translated only after the full English
    answer has been checked. `search_query` is the English text to search with; by default it
    is the question, translated to English if it is written in Kannada or Hindi script.
    Raises LLMUnavailableError.
    """
    question = to_ascii_digits(question.strip())
    history = [to_ascii_digits(q) for q in history]
    warnings: list[str] = []
    if search_query is None:
        if needs_translation(question):
            search_query, question_warnings = question_to_english(question, translator, llm)
            warnings += question_warnings
        else:
            search_query = question

    evidence = check_evidence(search_query, index.store, index.bm25, index.unavailable_files, history)
    warnings += evidence.notes
    if not evidence.ok:
        answer, translation_warnings, translated = localize_answer(evidence.message, language, translator)
        yield "result", {"answer": answer, "english_answer": evidence.message if language != "english" else None,
                         "translated": translated, "citations": [], "evidence_found": False,
                         "search_query": evidence.search_query, "warnings": warnings + translation_warnings}
        return

    # The LLM always answers in English, from the English question. That grounded answer is what
    # the citation checks look at; translation only happens afterwards.
    prompt_question = search_query if needs_translation(question) else question
    pieces = []
    for piece in generate_answer(llm, prompt_question, evidence, history):
        pieces.append(piece)
        if language == "english":
            yield "token", piece
    english = "".join(pieces).strip()
    cited, unknown = check_citations(english, evidence.results)
    if unknown:
        warnings.append("The answer cites pages that were not in the retrieved evidence: " + ", ".join(unknown))
    elif not cited:
        warnings.append("The answer has no citations.")
    unsupported = unsupported_standard_numbers(english, evidence.results, evidence.notes)
    if unsupported:
        warnings.append("The answer names standards that are not in the indexed evidence: " + ", ".join(unsupported))

    answer, translation_warnings, translated = localize_answer(english, language, translator)
    yield "result", {"answer": answer, "english_answer": english if language != "english" else None,
                     "translated": translated, "citations": [to_citation(r) for r in cited], "evidence_found": True,
                     "search_query": evidence.search_query, "warnings": warnings + translation_warnings}


def answer_question(
    question: str,
    language: Language,
    history: list[str],
    index: SearchIndex,
    llm: LLMProvider,
    translator: TranslationProvider | None,
    search_query: str | None = None,
) -> dict:
    """The full answer from iter_answer, without streaming. Raises LLMUnavailableError."""
    for kind, value in iter_answer(question, language, history, index, llm, translator, search_query):
        if kind == "result":
            return value
    raise RuntimeError("The answer pipeline ended without a result.")


def parse_language(value: str) -> Language:
    language = value.strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(422, f"Unsupported language '{value}'. Use one of: {', '.join(SUPPORTED_LANGUAGES)}.")
    return language


def read_audio(file: UploadFile) -> bytes:
    audio = file.file.read(config.MAX_AUDIO_BYTES + 1)
    if not audio:
        raise HTTPException(400, "The audio file is empty.")
    if len(audio) > config.MAX_AUDIO_BYTES:
        raise HTTPException(413, f"The audio file is larger than {config.MAX_AUDIO_BYTES // (1024 * 1024)} MB.")
    return audio


def stt_error(exc: STTError) -> HTTPException:
    # A missing key is a server setup problem (503). Anything else is a Sarvam-side failure (502).
    return HTTPException(503 if not config.SARVAM_API_KEY else 502, str(exc))


def run_stt(audio: bytes, file: UploadFile, language: Language, mode: str, index: SearchIndex) -> Transcript:
    return transcribe(
        audio,
        file.filename or "audio.wav",
        indexed_is_numbers(index.titles),
        language_code=SUPPORTED_LANGUAGES[language],
        mode=mode,
        content_type=file.content_type or "audio/wav",
    )


# ---------- Endpoints ----------


@app.get("/api/health")
def health() -> dict:
    """Liveness check. Does not touch the index, the LLM or Sarvam."""
    return {"status": "ok"}


@app.get("/api/status")
def status(index: SearchIndex = Depends(get_search_index), llm: LLMProvider = Depends(get_llm_provider)) -> dict:
    """Readiness of each component: index, local LLM, speech-to-text and translation."""
    try:
        llm.check()
        llm_available, llm_error = True, None
    except LLMUnavailableError as exc:
        llm_available, llm_error = False, str(exc)
    sarvam_configured = bool(config.SARVAM_API_KEY)
    return {
        "llm": {"provider": llm.name, "model": llm.model, "available": llm_available, "error": llm_error},
        "stt": {"provider": "sarvam", "model": config.SARVAM_STT_MODEL, "configured": sarvam_configured},
        "translation": {"provider": "sarvam", "model": config.SARVAM_TRANSLATE_MODEL, "configured": sarvam_configured},
        "index": {
            "chunks": len(index.bm25.chunks),
            "documents": index.titles,
            "unavailable_files": index.unavailable_files,
        },
        "supported_languages": SUPPORTED_LANGUAGES,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    index: SearchIndex = Depends(get_search_index),
    llm: LLMProvider = Depends(get_llm_provider),
    translator: TranslationProvider | None = Depends(get_translation_provider),
) -> ChatResponse:
    """Answer a typed question from the indexed BIS documents, in the chosen language."""
    try:
        result = answer_question(request.question, request.language, request.history, index, llm, translator)
    except LLMUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    return ChatResponse(language=request.language, model=llm.model, **result)


@app.post("/api/chat/stream")
def chat_stream(
    request: ChatRequest,
    index: SearchIndex = Depends(get_search_index),
    llm: LLMProvider = Depends(get_llm_provider),
    translator: TranslationProvider | None = Depends(get_translation_provider),
) -> StreamingResponse:
    """Like /api/chat, but streams newline-delimited JSON events:

    - {"type": "token", "text": "..."} while an English answer is written (not for Kannada or Hindi)
    - {"type": "done", "response": {...}} with the same body /api/chat returns
    - {"type": "error", "status": 503, "detail": "..."} if the LLM is unavailable
    """

    def events() -> Iterator[str]:
        try:
            for kind, value in iter_answer(request.question, request.language, request.history, index, llm, translator):
                if kind == "token":
                    yield json.dumps({"type": "token", "text": value}, ensure_ascii=False) + "\n"
                else:
                    response = ChatResponse(language=request.language, model=llm.model, **value)
                    yield json.dumps({"type": "done", "response": response.model_dump()}, ensure_ascii=False) + "\n"
        except LLMUnavailableError as exc:
            yield json.dumps({"type": "error", "status": 503, "detail": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.post("/api/speech-to-text", response_model=SpeechToTextResponse)
def speech_to_text(
    file: UploadFile = File(..., description="Audio recording, under 30 seconds."),
    language: str = Form("english", description="Spoken language: english, kannada or hindi."),
    index: SearchIndex = Depends(get_search_index),
) -> SpeechToTextResponse:
    """Transcribe a recording in the chosen language with Sarvam."""
    language = parse_language(language)
    audio = read_audio(file)
    try:
        transcript = run_stt(audio, file, language, "transcribe", index)
    except STTError as exc:
        raise stt_error(exc) from exc
    return SpeechToTextResponse(
        transcript=transcript.text, language=language, language_code=SUPPORTED_LANGUAGES[language], provider="sarvam"
    )


@app.post("/api/voice-chat", response_model=VoiceChatResponse)
def voice_chat(
    file: UploadFile = File(..., description="Audio recording, under 30 seconds."),
    language: str = Form("english", description="Spoken and answer language: english, kannada or hindi."),
    history: list[str] = Form(default=[], description="Earlier user questions, oldest first."),
    index: SearchIndex = Depends(get_search_index),
    llm: LLMProvider = Depends(get_llm_provider),
    translator: TranslationProvider | None = Depends(get_translation_provider),
) -> VoiceChatResponse:
    """Transcribe a spoken question with Sarvam, then answer it like /api/chat."""
    language = parse_language(language)
    audio = read_audio(file)
    try:
        if language == "english":
            heard = run_stt(audio, file, language, "transcribe", index)
            search_query = heard.text
        else:
            with ThreadPoolExecutor(max_workers=2) as pool:
                heard_job = pool.submit(run_stt, audio, file, language, "transcribe", index)
                english_job = pool.submit(run_stt, audio, file, language, "translate", index)
                heard, search_query = heard_job.result(), english_job.result().text
    except STTError as exc:
        raise stt_error(exc) from exc

    try:
        result = answer_question(heard.text, language, history, index, llm, translator, search_query=search_query)
    except LLMUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    return VoiceChatResponse(
        transcript=heard.text, language=language, stt_provider="sarvam", llm_provider=llm.name, model=llm.model, **result
    )
