"""Streamlit chat UI for the BIS assistant.

Run from the project root:  streamlit run app.py
"""

from pathlib import Path

import streamlit as st

import config
from src.assistant import (
    EVIDENCE_ONLY_MESSAGE,
    INSUFFICIENT_ANSWER,
    check_citations,
    check_evidence,
    generate_answer,
    indexed_standards,
    standard_label,
    unsupported_standard_numbers,
)
from src.llm import LLMUnavailableError, get_llm
from src.retrieval import build_bm25_index, load_indexed_chunks, load_unavailable_files, open_vector_store
from src.stt import STTError, indexed_is_numbers, transcribe

EVIDENCE_LABELS = {
    "answer": "Retrieved evidence",
    "evidence_only": "Most relevant passages",
    "refusal": "Closest passages (not used)",
}

st.set_page_config(page_title="BIS Assistant", page_icon="📘")


@st.cache_resource(show_spinner="Loading the BIS document index...")
def load_search_index(persist_dir: str, collection: str):
    """Open Chroma and build BM25 once per server process. Restart the app after rebuilding the index."""
    store = open_vector_store(Path(persist_dir), collection)
    return store, build_bm25_index(load_indexed_chunks(store))


def render_extras(message: dict) -> None:
    """Show notes, citations and retrieved passages under an assistant message."""
    for note in message.get("notes", []):
        st.info(note)
    results = message.get("results", [])
    if not results:
        return

    if message["kind"] == "answer":
        cited, unknown = check_citations(message["content"], results)
        if cited:
            st.markdown("**Sources**")
            for result in cited:
                st.markdown(f"- {standard_label(result.title, result.source)}, page {result.page} (`{result.source}`)")
                st.caption(" ".join(result.text.split())[:200] + "...")
        if unknown:
            st.warning("The answer cites pages that were not in the retrieved evidence: " + ", ".join(unknown))
        elif not cited and INSUFFICIENT_ANSWER not in message["content"].replace("’", "'"):
            st.warning("This answer has no citations. Treat it with caution.")
        unsupported = unsupported_standard_numbers(message["content"], results, message.get("notes", []))
        if unsupported:
            st.warning(
                "The answer names standards that are not in the indexed evidence: "
                + ", ".join(unsupported)
                + ". They were not checked. Confirm them with BIS before relying on them."
            )

    label = EVIDENCE_LABELS[message["kind"]]
    with st.expander(f"{label} ({len(results)})", expanded=message["kind"] == "evidence_only"):
        for number, result in enumerate(results, start=1):
            st.markdown(f"**{number}. {result.source}, page {result.page}** · found by {' + '.join(result.methods)}")
            st.text(result.text)


def voice_caption(voice: dict) -> str:
    translated = voice["mode"] == "translate" and voice["language"] != "English"
    action = "transcribed and translated to English" if translated else "transcribed"
    return f"🎤 Voice question in {voice['language']}, {action} by Sarvam AI"


def read_question(submission, titles: list[str]) -> tuple[str | None, dict | None]:
    """Turn the chat input into question text. A voice recording is transcribed first."""
    if submission is None:
        return None, None
    if isinstance(submission, str):
        return submission.strip() or None, None
    if submission.audio is None:
        return submission.text.strip() or None, None
    try:
        with st.spinner("Transcribing your voice question..."):
            transcript = transcribe(
                submission.audio.getvalue(), submission.audio.name or "question.wav", indexed_is_numbers(titles)
            )
    except STTError as exc:
        st.error(f"Voice input failed: {exc}")
        return None, None
    return transcript.text, {"language": transcript.language_name, "mode": config.SARVAM_STT_MODE}


st.title("BIS Assistant")
st.caption(
    "Ask about Indian Standards and BIS services. Answers come only from the indexed BIS documents, "
    "with page citations. Always confirm official requirements with BIS."
)

store, bm25_index = load_search_index(str(config.CHROMA_DIR), config.CHROMA_COLLECTION)
unavailable_files = load_unavailable_files(config.INGESTION_REPORT)
titles = indexed_standards(bm25_index.chunks)
voice_enabled = bool(config.SARVAM_API_KEY)
llm = get_llm()
try:
    llm.check()
    llm_error = None
except LLMUnavailableError as exc:
    llm_error = str(exc)

with st.sidebar:
    st.subheader("Knowledge base")
    for title in titles:
        st.markdown(f"- {title}")
    if unavailable_files:
        st.markdown("**Not searchable**")
        for name, reason in unavailable_files.items():
            st.caption(f"{name}: {reason}")
    st.caption(f"Model: `{llm.model}` via {llm.name}")
    if voice_enabled:
        st.caption("Voice input: on. Recordings are sent to Sarvam AI (cloud) for transcription.")
    else:
        st.caption("Voice input: off. Add SARVAM_API_KEY to .env to turn it on.")

if not bm25_index.chunks:
    st.warning("No documents are indexed yet. Add PDFs to `data/raw/`, then run:\n\n`python -m src.retrieval --rebuild`")
    st.stop()
if llm_error:
    st.error(f"**Local LLM not available.** {llm_error}")
    st.info("You can still ask questions. You will see the most relevant passages without a generated answer.")

messages: list[dict] = st.session_state.setdefault("messages", [])
for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("voice"):
            st.caption(voice_caption(message["voice"]))
        if message["role"] == "assistant":
            render_extras(message)

submission = st.chat_input(
    "Ask about a product, an IS number or BIS certification",
    accept_audio=voice_enabled,
)
question, voice = read_question(submission, titles)

if question:
    previous_questions = [m["content"] for m in messages if m["role"] == "user"]
    messages.append({"role": "user", "content": question, "voice": voice})
    with st.chat_message("user"):
        st.markdown(question)
        if voice:
            st.caption(voice_caption(voice))

    with st.chat_message("assistant"):
        with st.spinner("Searching the BIS documents..."):
            evidence = check_evidence(question, store, bm25_index, unavailable_files, previous_questions)
        reply = {"role": "assistant", "results": evidence.results, "notes": evidence.notes}
        if not evidence.ok:
            reply.update(kind="refusal", content=evidence.message)
            st.markdown(reply["content"])
        elif llm_error:
            reply.update(kind="evidence_only", content=EVIDENCE_ONLY_MESSAGE)
            st.markdown(reply["content"])
        else:
            try:
                with st.spinner("The local model is reading the evidence and writing an answer..."):
                    answer = st.write_stream(generate_answer(llm, question, evidence, previous_questions))
                reply.update(kind="answer", content=answer)
            except LLMUnavailableError as exc:
                reply.update(kind="evidence_only", content=f"{exc} {EVIDENCE_ONLY_MESSAGE}")
                st.markdown(reply["content"])
        render_extras(reply)
    messages.append(reply)
