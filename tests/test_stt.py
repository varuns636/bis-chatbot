"""Speech-to-text tests. The Sarvam API is faked; tests never send audio or the real key anywhere."""

import re
from pathlib import Path

import pytest

import config
from src import stt
from src.stt import STTError, indexed_is_numbers, normalize_transcript, transcribe

TEST_KEY = "test-key-123"
TITLES = ["IS 14543 (2004): Packaged Drinking Water", "IS 7098-1 (1988): Crosslinked polyethylene cables"]
AUDIO = b"RIFF fake wav bytes"


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


@pytest.fixture
def sarvam(monkeypatch):
    """Replace requests.post in src.stt. Set `.response`; inspect `.calls`."""

    class Fake:
        response = FakeResponse(200, {"transcript": "What is IS 14543?", "language_code": "en-IN", "language_probability": 1.0})
        calls: list[dict] = []

        @classmethod
        def post(cls, url, **kwargs):
            cls.calls.append({"url": url, **kwargs})
            return cls.response

    Fake.calls = []
    monkeypatch.setattr(stt.requests, "post", Fake.post)
    monkeypatch.setattr(config, "SARVAM_API_KEY", TEST_KEY)
    monkeypatch.setattr(config, "SARVAM_STT_MODEL", "saaras:v4")
    monkeypatch.setattr(config, "SARVAM_STT_MODE", "translate")
    return Fake


def test_transcribe_sends_audio_and_settings(sarvam):
    transcript = transcribe(AUDIO, "q.wav", {"14543", "7098"})

    call = sarvam.calls[0]
    assert call["url"] == config.SARVAM_STT_URL
    assert call["headers"] == {"api-subscription-key": TEST_KEY}
    assert call["files"]["file"] == ("q.wav", AUDIO, "audio/wav")
    assert call["data"] == {"model": "saaras:v4", "mode": "translate", "language_code": "unknown"}
    assert (transcript.text, transcript.language_code, transcript.language_name) == ("What is IS 14543?", "en-IN", "English")


def test_transcript_is_normalized_but_raw_text_is_kept(sarvam):
    sarvam.response = FakeResponse(200, {"transcript": "What is S14,543?", "language_code": "hi-IN"})

    transcript = transcribe(AUDIO, known_numbers={"14543"})

    assert transcript.raw_text == "What is S14,543?"
    assert transcript.text == "What is IS 14543?"
    assert transcript.language_name == "Hindi"


def test_missing_api_key_turns_voice_off(monkeypatch):
    monkeypatch.setattr(config, "SARVAM_API_KEY", "")

    with pytest.raises(STTError, match="SARVAM_API_KEY"):
        transcribe(AUDIO)


def test_empty_recording_is_rejected(sarvam):
    with pytest.raises(STTError, match="empty"):
        transcribe(b"")
    assert sarvam.calls == []


def test_rejected_key_message_never_contains_the_key(sarvam):
    sarvam.response = FakeResponse(403, {"error": {"message": f"invalid key {TEST_KEY}"}})

    with pytest.raises(STTError) as error:
        transcribe(AUDIO)

    assert "rejected" in str(error.value)
    assert TEST_KEY not in str(error.value)


def test_api_error_detail_is_shown(sarvam):
    sarvam.response = FakeResponse(400, {"error": {"message": "Audio longer than 30 seconds."}})

    with pytest.raises(STTError, match=r"\(HTTP 400\): Audio longer than 30 seconds"):
        transcribe(AUDIO)


def test_empty_transcript_is_reported(sarvam):
    sarvam.response = FakeResponse(200, {"transcript": "  ", "language_code": None})

    with pytest.raises(STTError, match="No speech"):
        transcribe(AUDIO)


def test_unreachable_service_is_reported(monkeypatch, closed_port_url):
    monkeypatch.setattr(config, "SARVAM_API_KEY", TEST_KEY)
    monkeypatch.setattr(config, "SARVAM_STT_URL", closed_port_url + "/speech-to-text")

    with pytest.raises(STTError, match="Cannot reach the Sarvam speech service"):
        transcribe(AUDIO)


@pytest.mark.parametrize(
    ("heard", "expected"),
    [
        ("What is S14,543?", "What is IS 14543?"),
        ("What is this 14,543?", "What is this IS 14543?"),
        ("Tell me about I.S. 7098", "Tell me about IS 7098"),
        ("What is IS 14543?", "What is IS 14543?"),
        ("What is is 14543?", "What is is 14543?"),
        ("The limit is 250 mg per litre", "The limit is 250 mg per litre"),
        ("Shelf life of 5,000 hours", "Shelf life of 5000 hours"),
    ],
)
def test_normalize_transcript(heard, expected):
    assert normalize_transcript(heard, {"14543", "7098"}) == expected


def test_indexed_is_numbers_come_from_titles():
    assert indexed_is_numbers(TITLES) == {"14543", "7098"}


def test_env_example_never_contains_a_real_key():
    text = (Path(__file__).resolve().parent.parent / ".env.example").read_text()
    assert re.search(r"^SARVAM_API_KEY=\s*$", text, re.MULTILINE)
