"""FastAPI tests. Sarvam (speech-to-text and translation) and Ollama are faked; retrieval runs on a small temporary index."""

import json

import pytest
from fastapi.testclient import TestClient

import config
from src import stt
from src.api import SearchIndex, app, get_llm_provider, get_search_index, get_translation_provider
from src.assistant import WEAK_EVIDENCE_MESSAGE, indexed_standards
from src.languages import SUPPORTED_LANGUAGES
from src.llm import LLMUnavailableError
from src.retrieval import build_bm25_index, build_vector_index, get_embeddings, open_vector_store
from src.translation import TranslationError
from test_retrieval import CHUNKS

KEY = "test-sarvam-key"
WATER_QUESTION = "What are the microbiological requirements for packaged drinking water?"
KANNADA_QUESTION = "ಪ್ಯಾಕೇಜ್ ಮಾಡಿದ ಕುಡಿಯುವ ನೀರಿನ ಸೂಕ್ಷ್ಮಜೀವಶಾಸ್ತ್ರೀಯ ಅವಶ್ಯಕತೆಗಳು ಯಾವುವು?"
HINDI_QUESTION = "पैकेज्ड पीने के पानी की सूक्ष्मजीवविज्ञानी आवश्यकताएं क्या हैं?"
CITATION = "[Source: is.14543.2004.pdf, page 5]"
ANSWER = f"It must be free from E. coli {CITATION}."
SCRIPT_WORD = {"kn-IN": "ಕನ್ನಡ", "hi-IN": "हिंदी", "en-IN": "English"}
AUDIO = b"RIFF fake audio bytes"


class FakeLLM:
    """Stands in for Ollama. Translation prompts get `translations`; answer prompts get `answer`."""

    name = "ollama"
    model = "gemma3:4b"

    def __init__(self):
        self.available = True
        self.answer = ANSWER
        self.translations: dict[str, str] = {}
        self.calls: list[list[dict]] = []

    def check(self):
        if not self.available:
            raise LLMUnavailableError("Cannot reach Ollama. Start it with `ollama serve`.")

    def stream_chat(self, messages):
        self.check()
        self.calls.append(messages)
        if messages[0]["content"].startswith("You are a translator"):
            yield self.translations.get(messages[1]["content"], f"[llm-translated] {messages[1]['content']}")
        else:
            yield self.answer

    def answer_prompts(self) -> list[str]:
        return [m[1]["content"] for m in self.calls if not m[0]["content"].startswith("You are a translator")]

    def translation_calls(self) -> list[list[dict]]:
        return [m for m in self.calls if m[0]["content"].startswith("You are a translator")]


class FakeTranslator:
    """Stands in for Sarvam translation. Marks text with a word in the target script, keeping placeholders."""

    name = "sarvam"
    model = "sarvam-translate:v1"

    def __init__(self):
        self.error: str | None = None
        self.replies: dict[str, str] = {}
        self.calls: list[dict] = []

    def translate(self, text, source_code, target_code):
        self.calls.append({"text": text, "source": source_code, "target": target_code})
        if self.error:
            raise TranslationError(self.error)
        return self.replies.get(text, f"{SCRIPT_WORD[target_code]} {text}")

    def answer_calls(self) -> list[dict]:
        return [c for c in self.calls if c["target"] != "en-IN"]


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture(scope="module")
def search_index(tmp_path_factory):
    store = open_vector_store(tmp_path_factory.mktemp("chroma"), "api", get_embeddings())
    build_vector_index(CHUNKS, store)
    unavailable = {"is.302.1.2008.pdf": "no usable text (79 of 80 pages blank; likely scanned, OCR needed)"}
    return SearchIndex(store, build_bm25_index(CHUNKS), unavailable, indexed_standards(CHUNKS))


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def translator():
    return FakeTranslator()


@pytest.fixture
def sarvam(monkeypatch):
    """Fake Sarvam speech-to-text API. Replies depend on the mode. Set `.status`; inspect `.calls`."""

    class Fake:
        status = 200
        replies = {"transcribe": WATER_QUESTION, "translate": WATER_QUESTION}
        calls: list[dict] = []

        @classmethod
        def post(cls, url, **kwargs):
            cls.calls.append(kwargs)
            if cls.status != 200:
                return FakeResponse(cls.status, {"error": {"message": f"upstream failure for {KEY}"}})
            data = kwargs["data"]
            return FakeResponse(200, {"transcript": cls.replies[data["mode"]], "language_code": data["language_code"]})

    Fake.calls = []
    monkeypatch.setattr(stt.requests, "post", Fake.post)
    return Fake


@pytest.fixture
def client(search_index, llm, translator, monkeypatch):
    monkeypatch.setattr(config, "SARVAM_API_KEY", KEY)
    app.dependency_overrides[get_search_index] = lambda: search_index
    app.dependency_overrides[get_llm_provider] = lambda: llm
    app.dependency_overrides[get_translation_provider] = lambda: translator
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def upload(language: str = "english", **extra):
    return {"files": {"file": ("q.wav", AUDIO, "audio/wav")}, "data": {"language": language, **extra}}


def translated(code: str, english: str = ANSWER) -> str:
    """What FakeTranslator makes of a one-line answer: the text is marked, the citation stays at the end."""
    body = english.replace(f" {CITATION}", "")
    return f"{SCRIPT_WORD[code]} {body} {CITATION}"


# ---------- Health and status ----------


def test_health(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_reports_index_llm_stt_translation_and_languages(client):
    body = client.get("/api/status").json()

    assert body["llm"] == {"provider": "ollama", "model": "gemma3:4b", "available": True, "error": None}
    assert body["stt"]["provider"] == "sarvam" and body["stt"]["configured"] is True
    assert body["translation"] == {"provider": "sarvam", "model": config.SARVAM_TRANSLATE_MODEL, "configured": True}
    assert body["index"]["chunks"] == len(CHUNKS)
    assert body["index"]["unavailable_files"] == {"is.302.1.2008.pdf": "no usable text (79 of 80 pages blank; likely scanned, OCR needed)"}
    assert body["supported_languages"] == {"english": "en-IN", "kannada": "kn-IN", "hindi": "hi-IN"}


def test_status_reports_llm_down(client, llm):
    llm.available = False

    body = client.get("/api/status").json()

    assert body["llm"]["available"] is False
    assert "ollama serve" in body["llm"]["error"]


def test_supported_languages_are_exactly_three():
    assert SUPPORTED_LANGUAGES == {"english": "en-IN", "kannada": "kn-IN", "hindi": "hi-IN"}


# ---------- Text chat ----------


def test_chat_english_is_unchanged_and_not_translated(client, llm, translator):
    response = client.post("/api/chat", json={"question": WATER_QUESTION})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == ANSWER
    assert body["language"] == "english"
    assert body["evidence_found"] is True
    assert body["model"] == "gemma3:4b"
    assert body["search_query"] == WATER_QUESTION
    assert body["warnings"] == []
    assert body["english_answer"] is None and body["translated"] is False
    assert body["citations"] == [{
        "source": "is.14543.2004.pdf", "page": 5, "standard": "IS 14543 (2004)",
        "title": "IS 14543 (2004): Packaged Drinking Water",
        "preview": "5.1 Microbiological requirements. Packaged drinking water shall be free from E. coli and coliform bacteria.",
    }]
    assert translator.calls == []
    assert llm.translation_calls() == []


@pytest.mark.parametrize(("language", "code"), [("kannada", "kn-IN"), ("hindi", "hi-IN"), ("Hindi", "hi-IN")])
def test_chat_translates_the_english_answer(client, llm, translator, language, code):
    body = client.post("/api/chat", json={"question": WATER_QUESTION, "language": language}).json()

    assert body["language"] == language.lower()
    assert body["answer"] == translated(code)
    assert body["english_answer"] == ANSWER
    assert body["translated"] is True
    assert body["warnings"] == []
    assert {(c["source"], c["target"]) for c in translator.calls} == {("en-IN", code)}
    prompt = llm.answer_prompts()[0]
    assert "Answer language" not in prompt  # the LLM answers in English
    assert prompt.endswith(f"Question: {WATER_QUESTION}")


def test_translation_receives_only_the_answer_text(client, llm, translator):
    client.post("/api/chat", json={"question": WATER_QUESTION, "language": "kannada"})

    assert [c["text"] for c in translator.calls] == ["It must be free from __P0__."]


def test_citations_is_numbers_and_values_survive_translation(client, llm, translator):
    llm.answer = (
        f"- IS 14543:2004 requires water to be free from E. coli at 20 °C, see clause 5.1 {CITATION}.\n"
        "- Verify with BIS: check the current edition of IS 14543:2004."
    )

    body = client.post("/api/chat", json={"question": WATER_QUESTION, "language": "hindi"}).json()

    for term in ["IS 14543:2004", "E. coli", "20 °C", "5.1", CITATION]:
        assert term in body["answer"]
    assert body["answer"].count("IS 14543:2004") == 2
    assert [(c["source"], c["page"]) for c in body["citations"]] == [("is.14543.2004.pdf", 5)]
    for call in translator.calls:
        assert "14543" not in call["text"] and "[Source" not in call["text"] and "20" not in call["text"]


def test_translation_failure_returns_english_answer_with_warning(client, translator):
    translator.error = "Sarvam translation failed (HTTP 500)."

    response = client.post("/api/chat", json={"question": WATER_QUESTION, "language": "kannada"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == ANSWER
    assert body["translated"] is False
    assert body["evidence_found"] is True
    assert body["warnings"] == ["Translation to Kannada failed: Sarvam translation failed (HTTP 500). The answer is shown in English."]


def test_suspicious_translation_keeps_english_line_with_warning(client, translator):
    translator.replies["It must be free from __P0__."] = "ಕನ್ನಡ ಉತ್ತರ 99"

    body = client.post("/api/chat", json={"question": WATER_QUESTION, "language": "kannada"}).json()

    assert body["answer"] == ANSWER
    assert body["translated"] is False
    assert "1 of 1 lines are shown in English" in body["warnings"][0]


def test_missing_translator_returns_english_with_warning(client):
    app.dependency_overrides[get_translation_provider] = lambda: None

    body = client.post("/api/chat", json={"question": WATER_QUESTION, "language": "hindi"}).json()

    assert body["answer"] == ANSWER
    assert "not configured" in body["warnings"][0]


def test_kannada_question_is_translated_by_sarvam_for_search(client, llm, translator):
    translator.replies[KANNADA_QUESTION] = WATER_QUESTION

    body = client.post("/api/chat", json={"question": KANNADA_QUESTION, "language": "kannada"}).json()

    assert body["search_query"] == WATER_QUESTION
    assert body["evidence_found"] is True
    assert translator.calls[0] == {"text": KANNADA_QUESTION, "source": "kn-IN", "target": "en-IN"}
    assert llm.translation_calls() == []
    assert llm.answer_prompts()[0].endswith(f"Question: {WATER_QUESTION}")


def test_question_translation_falls_back_to_llm(client, llm, translator):
    translator.error = "Sarvam translation failed (HTTP 500)."
    llm.translations[HINDI_QUESTION] = WATER_QUESTION

    body = client.post("/api/chat", json={"question": HINDI_QUESTION, "language": "hindi"}).json()

    assert body["search_query"] == WATER_QUESTION
    assert body["evidence_found"] is True
    assert len(llm.translation_calls()) == 1
    assert "so the local LLM translated it" in body["warnings"][0]
    assert body["answer"] == ANSWER  # the answer translation failed too, so it stays English


def test_chat_refusal_in_english_and_hindi(client, llm, translator):
    english = client.post("/api/chat", json={"question": "What is the capital of France?"}).json()
    hindi = client.post("/api/chat", json={"question": "What is the capital of France?", "language": "hindi"}).json()

    assert english["evidence_found"] is False and english["citations"] == []
    assert english["answer"].startswith(WEAK_EVIDENCE_MESSAGE)
    assert hindi["evidence_found"] is False
    assert hindi["answer"].startswith("हिंदी " + WEAK_EVIDENCE_MESSAGE)
    assert hindi["english_answer"].startswith(WEAK_EVIDENCE_MESSAGE)
    assert "https://www.bis.gov.in" in hindi["answer"]
    assert llm.answer_prompts() == []


def test_chat_unavailable_scanned_standard(client):
    body = client.post("/api/chat", json={"question": "What is IS 302-1?"}).json()

    assert body["evidence_found"] is False
    assert "is.302.1.2008.pdf is in the document folder but was not searched" in body["answer"]


@pytest.mark.parametrize("language", ["tamil", "fr", "en-IN", ""])
def test_chat_rejects_unsupported_language(client, language):
    response = client.post("/api/chat", json={"question": WATER_QUESTION, "language": language})

    assert response.status_code == 422


def test_chat_rejects_empty_question(client):
    assert client.post("/api/chat", json={"question": "   "}).status_code == 422


def test_chat_returns_503_when_llm_is_down(client, llm):
    llm.available = False

    response = client.post("/api/chat", json={"question": WATER_QUESTION})

    assert response.status_code == 503
    assert "ollama serve" in response.json()["detail"]


# ---------- Speech-to-text ----------


@pytest.mark.parametrize(("language", "code"), [("english", "en-IN"), ("kannada", "kn-IN"), ("hindi", "hi-IN")])
def test_speech_to_text_maps_language(client, sarvam, language, code):
    sarvam.replies["transcribe"] = "transcribed text"

    response = client.post("/api/speech-to-text", **upload(language))

    assert response.status_code == 200
    assert response.json() == {"transcript": "transcribed text", "language": language, "language_code": code, "provider": "sarvam"}
    call = sarvam.calls[0]
    assert call["data"] == {"model": config.SARVAM_STT_MODEL, "mode": "transcribe", "language_code": code}
    assert call["headers"] == {"api-subscription-key": KEY}
    assert call["files"]["file"] == ("q.wav", AUDIO, "audio/wav")


def test_speech_to_text_converts_kannada_digits(client, sarvam):
    sarvam.replies["transcribe"] = "IS ೧೪೫೪೩ ಎಂದರೇನು?"

    body = client.post("/api/speech-to-text", **upload("kannada")).json()

    assert body["transcript"] == "IS 14543 ಎಂದರೇನು?"


@pytest.mark.parametrize("language", ["tamil", "bengali", "ta-IN"])
def test_speech_to_text_rejects_unsupported_language(client, sarvam, language):
    response = client.post("/api/speech-to-text", **upload(language))

    assert response.status_code == 422
    assert sarvam.calls == []


def test_speech_to_text_without_api_key(client, sarvam, monkeypatch):
    monkeypatch.setattr(config, "SARVAM_API_KEY", "")

    response = client.post("/api/speech-to-text", **upload("hindi"))

    assert response.status_code == 503
    assert "SARVAM_API_KEY" in response.json()["detail"]
    assert sarvam.calls == []


def test_speech_to_text_sarvam_failure(client, sarvam):
    sarvam.status = 500

    response = client.post("/api/speech-to-text", **upload("kannada"))

    assert response.status_code == 502
    assert "HTTP 500" in response.json()["detail"]


def test_speech_to_text_rejected_key_is_not_leaked(client, sarvam):
    sarvam.status = 403

    response = client.post("/api/speech-to-text", **upload("english"))

    assert response.status_code == 502
    assert KEY not in response.text


def test_speech_to_text_rejects_empty_audio(client, sarvam):
    response = client.post("/api/speech-to-text", files={"file": ("q.wav", b"", "audio/wav")}, data={"language": "english"})

    assert response.status_code == 400
    assert sarvam.calls == []


# ---------- Voice chat ----------


def test_voice_chat_hindi(client, sarvam, llm, translator):
    sarvam.replies = {"transcribe": HINDI_QUESTION, "translate": WATER_QUESTION}

    response = client.post("/api/voice-chat", **upload("hindi"))

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == HINDI_QUESTION
    assert body["answer"] == translated("hi-IN")
    assert body["english_answer"] == ANSWER
    assert body["language"] == "hindi"
    assert body["evidence_found"] is True
    assert body["stt_provider"] == "sarvam" and body["llm_provider"] == "ollama" and body["model"] == "gemma3:4b"
    assert body["search_query"] == WATER_QUESTION
    assert [c["page"] for c in body["citations"]] == [5]
    assert sorted(call["data"]["mode"] for call in sarvam.calls) == ["transcribe", "translate"]
    assert {call["data"]["language_code"] for call in sarvam.calls} == {"hi-IN"}
    assert llm.translation_calls() == []
    assert [c["target"] for c in translator.calls] == ["hi-IN"]  # only the answer; Sarvam STT gave the English query
    prompt = llm.answer_prompts()[0]
    assert "Answer language" not in prompt
    assert prompt.endswith(f"Question: {WATER_QUESTION}")


def test_voice_chat_kannada(client, sarvam, llm, translator):
    sarvam.replies = {"transcribe": KANNADA_QUESTION, "translate": WATER_QUESTION}

    body = client.post("/api/voice-chat", **upload("kannada")).json()

    assert body["transcript"] == KANNADA_QUESTION
    assert body["language"] == "kannada"
    assert body["answer"] == translated("kn-IN")
    assert body["evidence_found"] is True
    assert {call["data"]["language_code"] for call in sarvam.calls} == {"kn-IN"}
    assert [c["target"] for c in translator.calls] == ["kn-IN"]


def test_voice_chat_english_uses_one_sarvam_call_and_no_translation(client, sarvam, translator):
    body = client.post("/api/voice-chat", **upload("english")).json()

    assert [call["data"]["mode"] for call in sarvam.calls] == ["transcribe"]
    assert body["transcript"] == body["search_query"] == WATER_QUESTION
    assert body["answer"] == ANSWER
    assert translator.calls == []


def test_voice_chat_uses_history_for_follow_ups(client, sarvam):
    sarvam.replies["transcribe"] = "What does it say about labels?"

    body = client.post("/api/voice-chat", **upload("english", history=["What is IS 7098?"])).json()

    assert body["search_query"] == "What does it say about labels? (IS 7098)"
    assert {c["source"] for c in body["citations"]} <= {"is.7098.1.1988.pdf"}


def test_voice_chat_translation_failure_returns_english(client, sarvam, translator):
    sarvam.replies = {"transcribe": HINDI_QUESTION, "translate": WATER_QUESTION}
    translator.error = "Cannot reach the Sarvam translation service (ConnectionError)."

    response = client.post("/api/voice-chat", **upload("hindi"))

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == ANSWER
    assert body["translated"] is False
    assert "Translation to Hindi failed" in body["warnings"][0]


def test_voice_chat_rejects_unsupported_language(client, sarvam):
    assert client.post("/api/voice-chat", **upload("tamil")).status_code == 422
    assert sarvam.calls == []


def test_voice_chat_without_api_key(client, sarvam, monkeypatch):
    monkeypatch.setattr(config, "SARVAM_API_KEY", "")

    response = client.post("/api/voice-chat", **upload("kannada"))

    assert response.status_code == 503
    assert "SARVAM_API_KEY" in response.json()["detail"]


def test_voice_chat_sarvam_failure(client, sarvam, llm):
    sarvam.status = 500

    response = client.post("/api/voice-chat", **upload("hindi"))

    assert response.status_code == 502
    assert llm.calls == []


def test_voice_chat_returns_503_when_llm_is_down(client, sarvam, llm):
    llm.available = False

    response = client.post("/api/voice-chat", **upload("english"))

    assert response.status_code == 503


# ---------- Streaming chat ----------


def stream_events(client, body: dict) -> list[dict]:
    with client.stream("POST", "/api/chat/stream", json=body) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        return [json.loads(line) for line in response.iter_lines() if line]


def test_chat_stream_english_sends_tokens_then_the_chat_response(client):
    events = stream_events(client, {"question": WATER_QUESTION})

    assert [e["text"] for e in events if e["type"] == "token"] == [ANSWER]
    assert events[-1]["type"] == "done"
    assert events[-1]["response"] == client.post("/api/chat", json={"question": WATER_QUESTION}).json()


def test_chat_stream_kannada_sends_only_the_translated_response(client, translator):
    events = stream_events(client, {"question": WATER_QUESTION, "language": "kannada"})

    assert [e["type"] for e in events] == ["done"]
    assert events[0]["response"]["answer"] == translated("kn-IN")
    assert events[0]["response"]["citations"][0]["page"] == 5


def test_chat_stream_refusal_has_no_tokens(client):
    events = stream_events(client, {"question": "What is the capital of France?"})

    assert [e["type"] for e in events] == ["done"]
    assert events[0]["response"]["evidence_found"] is False


def test_chat_stream_reports_llm_down_as_error_event(client, llm):
    llm.available = False

    events = stream_events(client, {"question": WATER_QUESTION})

    assert events == [{"type": "error", "status": 503, "detail": "Cannot reach Ollama. Start it with `ollama serve`."}]


def test_chat_stream_rejects_unsupported_language(client):
    assert client.post("/api/chat/stream", json={"question": WATER_QUESTION, "language": "tamil"}).status_code == 422


# ---------- CORS ----------


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_cors_allows_vite_dev_server(client, origin):
    preflight = client.options(
        "/api/chat", headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    )
    simple = client.get("/api/health", headers={"Origin": origin})

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert simple.headers["access-control-allow-origin"] == origin


def test_cors_blocks_other_origins(client):
    preflight = client.options("/api/chat", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    simple = client.get("/api/health", headers={"Origin": "http://evil.example"})

    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers
    assert "access-control-allow-origin" not in simple.headers
