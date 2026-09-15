"""Phase 4 tests for the LLM provider. A fake Ollama server stands in for the real one."""

import pytest

import config
from src.llm import LLMUnavailableError, OllamaProvider, get_llm

MESSAGES = [{"role": "user", "content": "Hi"}]


def chat_body(fake_ollama) -> dict:
    return [r for r in fake_ollama.requests if r["path"] == "/api/chat"][-1]["body"]


def test_get_llm_returns_ollama_without_any_api_key(monkeypatch):
    for name in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OLLAMA_API_KEY"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(config, "OLLAMA_THINK", False)

    llm = get_llm()

    assert isinstance(llm, OllamaProvider)
    assert llm.model == config.OLLAMA_MODEL
    assert llm.think is False


def test_ollama_requests_send_no_credentials(fake_ollama):
    llm = OllamaProvider("qwen3:4b", fake_ollama.url)
    llm.check()
    "".join(llm.stream_chat(MESSAGES))

    assert fake_ollama.requests
    for request in fake_ollama.requests:
        assert "Authorization" not in request["headers"]


def test_stream_chat_yields_reply_and_sends_expected_payload(fake_ollama):
    fake_ollama.reply_pieces = ["Hel", "lo"]

    reply = "".join(OllamaProvider("qwen3:4b", fake_ollama.url).stream_chat(MESSAGES))

    assert reply == "Hello"
    body = chat_body(fake_ollama)
    assert body["model"] == "qwen3:4b"
    assert body["messages"] == MESSAGES
    assert body["stream"] is True


def test_thinking_is_disabled_by_default(fake_ollama):
    "".join(OllamaProvider("qwen3:4b", fake_ollama.url).stream_chat(MESSAGES))

    assert chat_body(fake_ollama)["think"] is False


def test_enabled_thinking_is_not_shown_in_reply(fake_ollama):
    fake_ollama.thinking_pieces = ["Hmm, the user wants ", "a short reply."]
    fake_ollama.reply_pieces = ["BIS OK"]

    reply = "".join(OllamaProvider("qwen3:4b", fake_ollama.url, think=True).stream_chat(MESSAGES))

    assert reply == "BIS OK"
    assert chat_body(fake_ollama)["think"] is True


def test_non_thinking_model_gets_no_think_flag(fake_ollama):
    fake_ollama.capabilities = ["completion"]

    "".join(OllamaProvider("qwen3:4b-instruct", fake_ollama.url, think=True).stream_chat(MESSAGES))

    assert "think" not in chat_body(fake_ollama)


def test_check_reports_missing_model(fake_ollama):
    fake_ollama.models = ["qwen3:latest"]

    with pytest.raises(LLMUnavailableError, match="ollama pull qwen3:4b"):
        OllamaProvider("qwen3:4b", fake_ollama.url).check()


def test_check_reports_unreachable_server(closed_port_url):
    with pytest.raises(LLMUnavailableError) as error:
        OllamaProvider("qwen3:4b", closed_port_url).check()

    assert "Cannot reach Ollama" in str(error.value)
    assert "ollama serve" in str(error.value)
    assert "ollama pull qwen3:4b" in str(error.value)


def test_unsupported_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "paid-cloud")

    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        get_llm()
