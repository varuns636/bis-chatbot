"""LLM providers. The rest of the app uses the LLMProvider interface, never a vendor API directly.

Only Ollama (local, no API key) is implemented. It is called over its HTTP API with the
standard library, so no extra package is needed.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Protocol

import config

# Low temperature keeps answers close to the evidence. num_ctx fits the system prompt,
# five evidence passages, any reasoning and the answer. num_predict caps the answer length, so a
# repetition loop (seen once in a Kannada answer) cannot run on for thousands of tokens.
OLLAMA_OPTIONS = {"temperature": 0.1, "num_ctx": 8192, "num_predict": 1500}


class LLMUnavailableError(RuntimeError):
    """The LLM cannot be used. The message tells the user how to fix it."""


class LLMProvider(Protocol):
    name: str
    model: str

    def check(self) -> None:
        """Raise LLMUnavailableError if the model cannot answer right now."""

    def stream_chat(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Send chat messages and yield the reply in pieces."""


class OllamaProvider:
    """Chat with a model served by a local Ollama server."""

    name = "ollama"

    def __init__(self, model: str, base_url: str, timeout: float = 120.0, think: bool = False) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.think = think
        self._thinking: bool | None = None  # read from Ollama on first use

    def _setup_help(self) -> str:
        return (
            "Install Ollama from https://ollama.com/download (or run `brew install ollama`). "
            "Start it with the Ollama app or `ollama serve`. "
            f"Then download the model: `ollama pull {self.model}`"
        )

    def _open(self, path: str, payload: dict | None = None, timeout: float | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            return urllib.request.urlopen(request, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace").strip()
            if exc.code == 404 and "not found" in detail:
                raise LLMUnavailableError(f"Ollama cannot find model '{self.model}'. Run: `ollama pull {self.model}`") from exc
            raise LLMUnavailableError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:  # connection refused, bad host, timeout
            reason = getattr(exc, "reason", exc)
            raise LLMUnavailableError(f"Cannot reach Ollama at {self.base_url} ({reason}). {self._setup_help()}") from exc

    def supports_thinking(self) -> bool:
        """True if Ollama lists "thinking" among the model's capabilities. Cached after the first call."""
        if self._thinking is None:
            with self._open("/api/show", {"model": self.model}, timeout=10) as response:
                self._thinking = "thinking" in json.load(response).get("capabilities", [])
        return self._thinking

    def check(self) -> None:
        with self._open("/api/tags", timeout=3) as response:
            installed = {model["name"] for model in json.load(response).get("models", [])}
        if self.model not in installed and f"{self.model}:latest" not in installed:
            raise LLMUnavailableError(
                f"Ollama is running, but model '{self.model}' is not installed. Run: `ollama pull {self.model}`"
            )
        self.supports_thinking()

    def stream_chat(self, messages: list[dict[str, str]]) -> Iterator[str]:
        payload = {"model": self.model, "messages": messages, "stream": True, "options": OLLAMA_OPTIONS}
        if self.supports_thinking():
            # think=true: Ollama returns the reasoning in a separate "thinking" field, which is dropped
            # here, so users see only the answer. think=false: hybrid models such as qwen3:latest skip
            # reasoning. Thinking-only models such as qwen3:4b ignore it and mix reasoning into the answer.
            payload["think"] = self.think
        with self._open("/api/chat", payload) as response:
            try:
                for line in response:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise LLMUnavailableError(f"Ollama error: {event['error']}")
                    piece = event.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if event.get("done"):
                        break
            except OSError as exc:  # the connection dropped or timed out mid-answer
                raise LLMUnavailableError(f"Ollama stopped responding ({exc}).") from exc


def get_llm() -> LLMProvider:
    """Return the provider selected by LLM_PROVIDER."""
    if config.LLM_PROVIDER == "ollama":
        return OllamaProvider(config.OLLAMA_MODEL, config.OLLAMA_BASE_URL, config.OLLAMA_TIMEOUT, config.OLLAMA_THINK)
    raise ValueError(f"Unsupported LLM_PROVIDER {config.LLM_PROVIDER!r}. Supported: 'ollama'.")
