# BIS Assistant

AI assistant for Indian Standards and BIS services. It helps industries and consumers find relevant standards and understand certification, with answers grounded in official BIS documents and cited by document name and page.

Smart India Hackathon prototype. Status: Phase 4 (local LLM chatbot).

## Requirements

- macOS
- Python 3.11 (`brew install python@3.11`)
- [Ollama](https://ollama.com/download) for the local LLM (no API key needed)

## Setup

```bash
cd bis-chatbot
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Local LLM:

```bash
brew install ollama        # or install the Ollama app from ollama.com/download
ollama serve               # skip if the Ollama app is already running
ollama pull gemma3:4b      # default model; set OLLAMA_MODEL in .env to change it
```

## Add documents

Put only permitted, legally accessible BIS PDFs in `data/raw/`. Subfolders are allowed. Do not commit or redistribute copyrighted standards.

## Build the index

```bash
python -m src.retrieval --rebuild
```

This reads every PDF in `data/raw/`, splits the text into chunks and indexes them. Each chunk keeps its file name, path, page number and title for citations. Corrupted, duplicate and scanned PDFs are skipped with a reason, and the run continues. Skipped files are listed in `data/chroma/ingestion_report.json`, and the chatbot tells users that those files were not searched.

The knowledge base holds more than the standards themselves. Ingestion also reads, from the heading at the top of each PDF:

- **the title**, when the PDF metadata has none. Press notes, product manuals and summary sheets usually do not.
- **the IS numbers the document is about**, so "IS 302" finds the IS 302-1 product manual and "IS 1417" finds the IS 1417 summary sheet. Only the heading is read, never the body, so a product manual that names IS 1293 for its plugs is not treated as a copy of IS 1293.
- **the document type**: Indian Standard, Act, product manual, press release, standard summary or plain BIS document.

The type is shown next to every citation and in the knowledge-base panel. When a standard is covered only by documents *about* it (IS 302-1, whose own PDF is scanned), the assistant is told to answer from those and to say the answer does not come from the standard itself.

Scanned (image-only) pages have no text layer, so they are skipped. OCR is not supported yet.

Run `--rebuild` after you add, change or remove PDFs, then restart the app. The first run downloads the embedding model (about 90 MB).

## Run the chatbot

```bash
streamlit run app.py
```

For each question, the app:

1. Searches the index with hybrid retrieval: `all-MiniLM-L6-v2` embeddings in ChromaDB plus BM25 keyword search.
2. Checks that the evidence is strong enough. Weak or unrelated evidence is refused, with the reason shown.
3. Sends only the retrieved passages to the local LLM, which must cite them as `[Source: file.pdf, page N]`.

If Ollama is not running, the app shows setup instructions and still shows the most relevant passages.

## Voice questions (optional)

The chat box has a microphone button when `SARVAM_API_KEY` is set in `.env`. A recording is sent to the [Sarvam AI](https://www.sarvam.ai) speech-to-text API. By default (`SARVAM_STT_MODE=translate`), speech in English or any of 22 Indian languages comes back as English text, then goes through the same local search and answer steps as a typed question.

- Only the audio leaves the machine. Search and answers stay local.
- Spoken IS numbers sometimes come back as "this 14,543" or "S14543". The app repairs these before searching. See `src/stt.py`.
- Recordings should be under 30 seconds.

## FastAPI backend

The API uses the same pipeline as the Streamlit app: hybrid retrieval, the evidence gate, the local Ollama model, citation checks and Sarvam speech-to-text. Both can run at the same time.

```bash
uvicorn src.api:app --reload --port 8000
curl http://127.0.0.1:8000/api/health
```

Interactive documentation: http://127.0.0.1:8000/docs. The API loads the index at startup, which takes about 20 seconds. Restart it after rebuilding the index.

### Languages

`language` must be one of `english`, `kannada` or `hindi` (case-insensitive). Any other value returns HTTP 422.

| language | Sarvam code |
|---|---|
| english | en-IN |
| kannada | kn-IN |
| hindi | hi-IN |

Search and answer generation always run in English, because the documents are English and the local model writes English reliably. For Kannada and Hindi:

1. The question becomes English. Typed Kannada or Hindi is translated with Sarvam; if Sarvam fails, the local LLM translates it. For voice, Sarvam transcribes the audio in the chosen language, and a second Sarvam call returns the English text used for search.
2. The local LLM writes a grounded answer in English. The citation and IS-number checks run on this English answer.
3. Only the answer text is translated with Sarvam (`sarvam-translate:v1`). Citations are taken out before translation and put back unchanged. IS references, numbers with units, clause numbers, file names, URLs and abbreviations such as HCl or PVC are replaced with placeholders, then restored.
4. Each translated line is checked: the placeholders and numbers must come back unchanged, and the text must be in the target script. A line that fails stays in English, with a warning.
5. If translation fails completely, the English answer is returned with a warning. The request does not fail.

English answers are not translated. Kannada and Hindi responses also include `english_answer` (the grounded English text) and `translated`.

### Endpoints

| Method | Path | Input | Returns |
|---|---|---|---|
| GET | `/api/health` | none | `{"status": "ok"}` |
| GET | `/api/status` | none | Index size and documents, LLM availability, whether speech-to-text and translation are configured, supported languages |
| POST | `/api/chat` | JSON `{"question", "language", "history"}` | `answer`, `language`, `citations`, `evidence_found`, `model`, `search_query`, `warnings`, `english_answer`, `translated` |
| POST | `/api/chat/stream` | same JSON as `/api/chat` | Newline-delimited JSON: `{"type": "token", "text"}` events while an English answer is written, then `{"type": "done", "response"}` (the `/api/chat` body) or `{"type": "error", "status", "detail"}` |
| POST | `/api/speech-to-text` | form: `file` (audio), `language` | `transcript`, `language`, `language_code`, `provider` |
| POST | `/api/voice-chat` | form: `file` (audio), `language`, optional repeated `history` | `transcript`, `answer`, `language`, `citations`, `evidence_found`, `stt_provider`, `llm_provider`, `model`, `search_query`, `warnings`, `english_answer`, `translated` |

`history` holds earlier user questions (oldest first), used to resolve follow-ups such as "what does it say about marking?".

Errors: `422` invalid input or language, `400` empty audio, `413` audio over 10 MB, `502` Sarvam failed, `503` Ollama not running or `SARVAM_API_KEY` missing.

Examples:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is IS 14543?", "language": "kannada"}'

curl -X POST http://127.0.0.1:8000/api/speech-to-text \
  -F "file=@question.wav" -F "language=hindi"

curl -X POST http://127.0.0.1:8000/api/voice-chat \
  -F "file=@question.wav" -F "language=kannada"
```

CORS allows `http://localhost:5173` and `http://127.0.0.1:5173` (the Vite dev server). Change this with `API_CORS_ORIGINS` in `.env`.

## Web frontend (React + Vite)

A separate web interface lives in `frontend/`. It calls the FastAPI backend above and never calls Sarvam directly.

```bash
# terminal 1: backend
uvicorn src.api:app --reload --port 8000

# terminal 2: frontend
cd frontend
npm install
npm run dev        # http://localhost:5173
```

The assistant page needs a session. `/login` offers a mobile number with a one-time code, a Gmail address, or **Continue as guest**. Sign-in is a browser-side demo: no SMS is sent, Google is not contacted, the code is shown on screen, and the API is open to everyone. Guest mode has the same access as a signed-in user. See `frontend/README.md` for details.

## Search from the command line

```bash
python -m src.retrieval "packaged drinking water"
python -m src.retrieval "IS 7098" -k 3
```

## Test

```bash
pytest
```

The tests use a fake Ollama server, so they do not need Ollama running.

## Configuration

All settings are in `.env` (see `.env.example`): model name, Ollama URL, chunk size, number of results, and the evidence thresholds `MIN_VECTOR_SCORE` and `MIN_KEYWORD_OVERLAP`.

## Project layout

```
app.py            Streamlit chat UI
config.py         Settings from environment variables / .env
src/ingestion.py  PDF reading, cleaning and chunking
src/retrieval.py  Vector, BM25 and hybrid search; index rebuild
src/assistant.py  Evidence gate, grounded prompt, citation checks
src/llm.py        LLM provider interface and Ollama client
src/stt.py        Speech-to-text through the Sarvam API
src/api.py        FastAPI backend (/api/health, /api/status, /api/chat, /api/speech-to-text, /api/voice-chat)
src/languages.py  Supported languages: english, kannada, hindi
src/translation.py Question and message translation with the local LLM
data/raw/         Source PDFs (not committed)
data/chroma/      Generated index and ingestion report (not committed)
tests/            Tests
```
