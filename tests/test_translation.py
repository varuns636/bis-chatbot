"""Answer translation tests. Sarvam is faked; tests never send text or the real key anywhere."""

import re

import pytest

import config
from src import translation
from src.translation import (
    SarvamTranslator,
    TranslationError,
    get_translator,
    localize_answer,
    mask,
    translate_text,
    unmask,
)

CITATION = "[Source: is.14543.2004.pdf, page 5]"
SCRIPT_WORD = {"kn-IN": "ಕನ್ನಡ", "hi-IN": "हिंदी", "en-IN": "English"}
ANSWER = (
    f"- IS 14543:2004 limits HCl to 20 % at 90°C under clause 5.1.1 {CITATION}.\n"
    "\n"
    "Uncertain: the evidence does not give the edition of is.14543.2004.pdf."
)
PROTECTED_TERMS = ["IS 14543:2004", "HCl", "20 %", "90°C", "5.1.1", CITATION, "is.14543.2004.pdf"]


class FakeTranslator:
    """Marks text as translated with a word in the target script and keeps the placeholders."""

    name = "sarvam"
    model = "fake"

    def __init__(self, reply=None, error: str | None = None):
        self.reply = reply
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    def translate(self, text, source_code, target_code):
        self.calls.append((text, source_code, target_code))
        if self.error:
            raise TranslationError(self.error)
        return self.reply(text) if self.reply else f"{SCRIPT_WORD[target_code]} {text}"


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_mask_hides_protected_terms_and_unmask_restores_them():
    text = "IS 14543:2004 limits HCl to 20 % at 90°C in clause 5.1.1 of is.14543.2004.pdf and IS 7098-1 (1988)."

    masked, tokens = mask(text)

    assert tokens == ["IS 14543:2004", "HCl", "20 %", "90°C", "5.1.1", "is.14543.2004.pdf", "IS 7098-1 (1988)"]
    assert not re.search(r"\d", re.sub(r"__P\d+__", "", masked))
    assert unmask(masked, tokens) == text


@pytest.mark.parametrize("translated", ["__P0__ only", "__P0__ __P0__ __P1__", "__P0__ __P1__ __P7__"])
def test_unmask_rejects_missing_repeated_or_unknown_placeholders(translated):
    assert unmask(translated, ["a", "b"]) is None


def test_translation_keeps_citations_is_numbers_and_values():
    fake = FakeTranslator()

    result = translate_text(ANSWER, "kn-IN", fake)

    first_line = result.text.splitlines()[0]
    assert first_line == f"- ಕನ್ನಡ IS 14543:2004 limits HCl to 20 % at 90°C under clause 5.1.1. {CITATION}"
    for term in PROTECTED_TERMS:
        assert term in result.text
    assert (result.translated, result.kept) == (2, 0)


def test_translator_receives_only_answer_text_without_protected_terms():
    fake = FakeTranslator()

    translate_text(ANSWER, "hi-IN", fake)

    sent = [text for text, _, _ in fake.calls]
    assert sent == [
        "__P0__ limits __P1__ to __P2__ at __P3__ under clause __P4__.",
        "Uncertain: the evidence does not give the edition of __P0__.",
    ]
    assert {(source, target) for _, source, target in fake.calls} == {("en-IN", "hi-IN")}


@pytest.mark.parametrize(
    "reply",
    [
        lambda text: f"ಕನ್ನಡ {text} 99",  # invents a number
        lambda text: "ಕನ್ನಡ ಉತ್ತರ",  # drops the placeholders
        lambda text: text,  # comes back untranslated
    ],
)
def test_suspicious_translations_keep_the_english_line(reply):
    result = translate_text(ANSWER, "kn-IN", FakeTranslator(reply))

    assert result.text == ANSWER
    assert (result.translated, result.kept) == (0, 2)


def test_localize_answer_leaves_english_untouched():
    fake = FakeTranslator()

    assert localize_answer(ANSWER, "english", fake) == (ANSWER, [], False)
    assert fake.calls == []


def test_localize_answer_falls_back_to_english_when_translation_fails():
    answer, warnings, translated = localize_answer(ANSWER, "hindi", FakeTranslator(error="Sarvam translation failed (HTTP 500)."))

    assert answer == ANSWER
    assert translated is False
    assert warnings == ["Translation to Hindi failed: Sarvam translation failed (HTTP 500). The answer is shown in English."]


def test_localize_answer_without_translator():
    answer, warnings, translated = localize_answer(ANSWER, "kannada", None)

    assert (answer, translated) == (ANSWER, False)
    assert "not configured" in warnings[0]


def test_localize_answer_warns_about_lines_kept_in_english():
    reply = lambda text: "ಕನ್ನಡ ಉತ್ತರ" if "evidence" in text else f"ಕನ್ನಡ {text}"  # noqa: E731

    answer, warnings, translated = localize_answer(ANSWER, "kannada", FakeTranslator(reply))

    assert translated is True
    assert answer.splitlines()[0].startswith("- ಕನ್ನಡ IS 14543:2004")
    assert answer.splitlines()[2] == ANSWER.splitlines()[2]
    assert warnings == ["1 of 2 lines are shown in English, because their Kannada translation changed a number, IS reference or technical term."]


def test_sarvam_translator_request(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(200, {"translated_text": "ಕನ್ನಡ ಪಠ್ಯ"})

    monkeypatch.setattr(translation.requests, "post", post)
    translator = SarvamTranslator("key-123", "https://api.sarvam.ai/translate", "sarvam-translate:v1", 30)

    assert translator.translate("Hello __P0__", "en-IN", "kn-IN") == "ಕನ್ನಡ ಪಠ್ಯ"
    url, kwargs = calls[0]
    assert url == "https://api.sarvam.ai/translate"
    assert kwargs["headers"] == {"api-subscription-key": "key-123"}
    assert kwargs["json"] == {
        "input": "Hello __P0__",
        "source_language_code": "en-IN",
        "target_language_code": "kn-IN",
        "model": "sarvam-translate:v1",
        "numerals_format": "international",
    }


@pytest.mark.parametrize(
    ("status", "payload", "message"),
    [
        (403, {"error": {"message": "invalid key key-123"}}, "key was rejected"),
        (500, {"error": {"message": "internal error"}}, r"\(HTTP 500\): internal error"),
        (200, {"translated_text": "  "}, "empty translation"),
    ],
)
def test_sarvam_translator_errors_never_contain_the_key(monkeypatch, status, payload, message):
    monkeypatch.setattr(translation.requests, "post", lambda url, **kwargs: FakeResponse(status, payload))

    with pytest.raises(TranslationError, match=message) as error:
        SarvamTranslator("key-123", "https://example.test/translate", "sarvam-translate:v1").translate("Hi", "en-IN", "hi-IN")

    assert "key-123" not in str(error.value)


def test_sarvam_translator_unreachable(closed_port_url):
    with pytest.raises(TranslationError, match="Cannot reach the Sarvam translation service"):
        SarvamTranslator("key", closed_port_url + "/translate", "sarvam-translate:v1").translate("Hi", "en-IN", "kn-IN")


def test_get_translator_needs_the_api_key(monkeypatch):
    monkeypatch.setattr(config, "SARVAM_API_KEY", "")
    assert get_translator() is None

    monkeypatch.setattr(config, "SARVAM_API_KEY", "key")
    translator = get_translator()
    assert isinstance(translator, SarvamTranslator)
    assert translator.model == config.SARVAM_TRANSLATE_MODEL
