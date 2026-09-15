"""Streamlit UI tests. They use a temporary index and a fake or unreachable Ollama, never a real LLM or Sarvam."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import config
from src.assistant import EVIDENCE_ONLY_MESSAGE, WEAK_EVIDENCE_MESSAGE
from src.retrieval import build_vector_index, get_embeddings, open_vector_store
from test_retrieval import CHUNKS

APP = str(Path(__file__).resolve().parent.parent / "app.py")
WATER_QUESTION = "What are the microbiological requirements for packaged drinking water?"


@pytest.fixture
def app_config(tmp_path, monkeypatch):
    """Point the app at an empty temporary index, with voice input off."""
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(config, "INGESTION_REPORT", tmp_path / "chroma" / "ingestion_report.json")
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(config, "OLLAMA_MODEL", "qwen3:4b")
    monkeypatch.setattr(config, "SARVAM_API_KEY", "")


@pytest.fixture
def indexed(app_config):
    build_vector_index(CHUNKS, open_vector_store(config.CHROMA_DIR, config.CHROMA_COLLECTION, get_embeddings()))


def run_app(*questions: str) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=60).run()
    for question in questions:
        app.chat_input[0].set_value(question).run()
    assert not app.exception
    return app


def text_of(elements) -> str:
    return "\n".join(str(element.value) for element in elements)


def test_app_without_index_shows_rebuild_command(app_config, closed_port_url, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_BASE_URL", closed_port_url)

    app = run_app()

    assert app.title[0].value == "BIS Assistant"
    assert "python -m src.retrieval --rebuild" in text_of(app.warning)


def test_app_without_ollama_shows_setup_help_and_passages(indexed, closed_port_url, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_BASE_URL", closed_port_url)

    app = run_app(WATER_QUESTION)

    assert "ollama pull qwen3:4b" in text_of(app.error)
    assert EVIDENCE_ONLY_MESSAGE in text_of(app.markdown)
    assert any(expander.label.startswith("Most relevant passages") for expander in app.expander)


def test_app_streams_grounded_answer_with_sources(indexed, fake_ollama, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_BASE_URL", fake_ollama.url)
    fake_ollama.reply_pieces = ["It must be free from E. coli ", "[Source: is.14543.2004.pdf, page 5]."]

    app = run_app(WATER_QUESTION)

    shown = text_of(app.markdown)
    assert "free from E. coli" in shown
    assert "IS 14543 (2004), page 5 (`is.14543.2004.pdf`)" in shown
    assert not app.error
    assert any(expander.label.startswith("Retrieved evidence") for expander in app.expander)


def test_app_refuses_unrelated_question_without_calling_llm(indexed, fake_ollama, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_BASE_URL", fake_ollama.url)

    app = run_app("What is the capital of France?")

    assert WEAK_EVIDENCE_MESSAGE in text_of(app.markdown)
    assert not [r for r in fake_ollama.requests if r["path"] == "/api/chat"]


def test_app_keeps_history_and_sends_only_user_questions(indexed, fake_ollama, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_BASE_URL", fake_ollama.url)
    fake_ollama.reply_pieces = ["UNSUPPORTED CLAIM FROM EARLIER ANSWER [Source: is.14543.2004.pdf, page 5]"]

    app = run_app("What is IS 14543?", "What does it say about bottles?")

    assert len(app.chat_message) == 4
    last_prompt = [r for r in fake_ollama.requests if r["path"] == "/api/chat"][-1]["body"]["messages"][1]["content"]
    assert "- What is IS 14543?" in last_prompt
    assert "UNSUPPORTED CLAIM" not in last_prompt


def test_app_shows_voice_input_off_without_key(indexed, fake_ollama, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_BASE_URL", fake_ollama.url)

    app = run_app()

    assert "Voice input: off" in text_of(app.sidebar.caption)


def test_app_with_voice_on_still_answers_typed_questions(indexed, fake_ollama, monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_BASE_URL", fake_ollama.url)
    monkeypatch.setattr(config, "SARVAM_API_KEY", "test-key")
    fake_ollama.reply_pieces = ["It must be free from E. coli [Source: is.14543.2004.pdf, page 5]."]

    app = run_app(WATER_QUESTION)

    assert "Voice input: on" in text_of(app.sidebar.caption)
    assert "free from E. coli" in text_of(app.markdown)
