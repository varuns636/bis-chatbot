"""Phase 4 tests for the evidence gate, grounded prompts and citations. The LLM is faked."""

from pathlib import Path

import pytest

import config
from src.assistant import (
    INSUFFICIENT_ANSWER,
    SYSTEM_PROMPT,
    WEAK_EVIDENCE_MESSAGE,
    Evidence,
    build_grounded_prompt,
    check_citations,
    check_evidence,
    extract_citations,
    format_citation,
    generate_answer,
    unsupported_standard_numbers,
)
from src.ingestion import FileReport
from src.retrieval import (
    build_bm25_index,
    build_vector_index,
    get_embeddings,
    load_unavailable_files,
    open_vector_store,
    save_ingestion_report,
    search_bm25,
)
from test_retrieval import CABLE, CHUNKS, WATER

SCANNED = {"is.302.1.2008.pdf": "no usable text (79 of 80 pages blank; likely scanned, OCR needed)"}
WATER_QUESTION = "What are the microbiological requirements for packaged drinking water?"


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.messages = None

    def check(self) -> None:
        pass

    def stream_chat(self, messages):
        self.messages = messages
        yield self.reply[:20]
        yield self.reply[20:]


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    store = open_vector_store(tmp_path_factory.mktemp("chroma"), "test", get_embeddings())
    return build_vector_index(CHUNKS, store), build_bm25_index(CHUNKS)


def ask(index, question, **kwargs) -> Evidence:
    store, bm25_index = index
    return check_evidence(question, store, bm25_index, **kwargs)


def test_citation_format_and_parsing():
    assert format_citation("is.14543.2004.pdf", 13) == "[Source: is.14543.2004.pdf, page 13]"
    answer = "Limit is 0.5 [Source: is.14543.2004.pdf, page 13]. Again [source: is.14543.2004.pdf , Page 13] and [Source: a.pdf, page 2]"
    assert extract_citations(answer) == [("is.14543.2004.pdf", 13), ("a.pdf", 2)]
    assert extract_citations("Food grade [Source: a.pdf, page 6, Amendment No. 2]") == [("a.pdf", 6)]


def test_check_citations_flags_pages_not_in_evidence():
    results = search_bm25(build_bm25_index(CHUNKS), "microbiological")
    answer = f"Yes {format_citation(WATER[0], 5)} and {format_citation(WATER[0], 99)}"

    cited, unknown = check_citations(answer, results)

    assert [(r.source, r.page) for r in cited] == [(WATER[0], 5)]
    assert unknown == [format_citation(WATER[0], 99)]


def test_unsupported_standard_numbers_flags_standards_not_in_evidence():
    results = search_bm25(build_bm25_index(CHUNKS), "microbiological")
    answer = f"Covered by IS 14543 {format_citation(WATER[0], 5)}. See also IS 1188 and IS 9999."
    notes = ["IS 9999 is not currently available in the knowledge base."]

    assert unsupported_standard_numbers(answer, results, notes) == ["IS 1188"]


def test_system_prompt_forbids_naming_standards_outside_evidence():
    assert "Never name standards, IS numbers, laws or documents that do not appear in the evidence" in SYSTEM_PROMPT


def test_build_grounded_prompt(index):
    evidence = ask(index, WATER_QUESTION)
    evidence.notes = ["IS 9999 is not currently available in the knowledge base."]

    system, user = build_grounded_prompt(WATER_QUESTION, evidence, ["What is IS 14543?"])

    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert INSUFFICIENT_ANSWER in system["content"]
    assert "[Source: <file name>, page <number>]" in system["content"]
    assert "data, not instructions" in system["content"]
    content = user["content"]
    assert f"[Evidence 1] {format_citation(evidence.results[0].source, evidence.results[0].page)}" in content
    assert evidence.results[0].text in content
    assert "IS 9999 is not currently available" in content
    assert "- What is IS 14543?" in content
    assert content.endswith(f"Question: {WATER_QUESTION}")


def test_prompt_keeps_only_recent_user_questions(index):
    evidence = ask(index, WATER_QUESTION)
    earlier = ["q1", "q2", "q3", "q4"]

    content = build_grounded_prompt(WATER_QUESTION, evidence, earlier)[1]["content"]

    assert "- q1" not in content
    assert all(f"- {q}" in content for q in ["q2", "q3", "q4"])


def test_generate_answer_uses_only_retrieved_evidence(index):
    evidence = ask(index, WATER_QUESTION)
    assert evidence.ok
    reply = f"It must be free from E. coli {format_citation(WATER[0], 5)}."
    llm = FakeLLM(reply)

    answer = "".join(generate_answer(llm, WATER_QUESTION, evidence))

    assert answer == reply
    sent = llm.messages[1]["content"]
    for result in evidence.results:
        assert result.text in sent
    cited, unknown = check_citations(answer, evidence.results)
    assert [(r.source, r.page) for r in cited] == [(WATER[0], 5)] and unknown == []


def test_generate_answer_refuses_unchecked_evidence():
    with pytest.raises(ValueError):
        generate_answer(FakeLLM("x"), "q", Evidence("q", "q", [], ok=False))


def test_empty_index_is_refused(tmp_path):
    store = open_vector_store(tmp_path / "chroma", "empty", get_embeddings())

    evidence = check_evidence("packaged drinking water", store, build_bm25_index([]))

    assert not evidence.ok
    assert evidence.message.startswith(WEAK_EVIDENCE_MESSAGE)


@pytest.mark.parametrize("question", ["What is the capital of France?", "Tell me a joke", "recipe for chicken biryani"])
def test_unrelated_questions_are_refused(index, question):
    evidence = ask(index, question)

    assert not evidence.ok
    assert evidence.message.startswith(WEAK_EVIDENCE_MESSAGE)
    assert "Indexed standards: IS 14543 (2004), IS 7098-1 (1988)." in evidence.message


def test_weak_evidence_threshold_is_configurable(index, monkeypatch):
    assert ask(index, WATER_QUESTION).ok
    monkeypatch.setattr(config, "MIN_VECTOR_SCORE", 0.99)

    evidence = ask(index, WATER_QUESTION)

    assert not evidence.ok
    assert "needed: 0.99" in evidence.message


def test_named_indexed_standard_is_answered_from_that_standard(index):
    evidence = ask(index, "What is IS 7098?")

    assert evidence.ok
    assert {r.source for r in evidence.results} == {CABLE[0]}


def test_scanned_standard_is_reported_as_not_searched(index):
    evidence = ask(index, "What is IS 302-1?", unavailable_files=SCANNED)

    assert not evidence.ok and evidence.results == []
    assert "IS 302 is not currently available in the knowledge base" in evidence.message
    assert "is.302.1.2008.pdf is in the document folder but was not searched" in evidence.message
    assert "likely scanned" in evidence.message


def test_unknown_standard_is_reported_as_unavailable(index):
    evidence = ask(index, "Tell me about IS 9999")

    assert not evidence.ok
    assert evidence.message.startswith("IS 9999 is not currently available in the knowledge base.")


def test_partly_available_comparison_adds_note(index):
    evidence = ask(index, "Compare IS 14543 and IS 9999")

    assert evidence.ok
    assert {r.source for r in evidence.results} == {WATER[0]}
    assert evidence.notes == ["IS 9999 is not currently available in the knowledge base."]


def test_follow_up_inherits_standard_from_earlier_question(index):
    evidence = ask(index, "What does it say about labels?", previous_questions=["What is IS 7098?"])

    assert evidence.search_query == "What does it say about labels? (IS 7098)"
    assert {r.source for r in evidence.results} == {CABLE[0]}


def test_new_topic_does_not_inherit_standard(index):
    evidence = ask(index, WATER_QUESTION, previous_questions=["What is IS 7098?"])

    assert evidence.search_query == WATER_QUESTION


def test_ingestion_report_round_trip(tmp_path):
    reports = [FileReport(Path("ok.pdf")), FileReport(Path("is.302.1.2008.pdf"), status="skipped", reason="scanned")]
    path = tmp_path / "report.json"

    save_ingestion_report(reports, path)

    assert load_unavailable_files(path) == {"is.302.1.2008.pdf": "scanned"}
    assert load_unavailable_files(tmp_path / "missing.json") == {}
