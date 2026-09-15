# BIS Assistant — Frontend

React + TypeScript + Vite + Tailwind CSS interface for the BIS Assistant. It talks only to the existing FastAPI backend (`../src/api.py`). Sarvam AI is called by the backend, never by the browser, so no API key is ever in the frontend.

## Run

Start the backend first, in one terminal:

```bash
cd ~/bis-chatbot
source venv/bin/activate
uvicorn src.api:app --reload --port 8000
```

Then the frontend, in a second terminal:

```bash
cd ~/bis-chatbot/frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server must run on port 5173, because the backend's CORS settings allow only `http://localhost:5173` and `http://127.0.0.1:5173`.

If the API runs somewhere else, copy `.env.example` to `.env.local` and change `VITE_API_BASE_URL`. Never put secrets in these files: `VITE_` variables end up in the public JavaScript bundle.

## Build

```bash
npm run build     # type-check, then build to dist/
npm run preview   # serve the build on http://localhost:5173
```

## Pages

- `/` — landing page: hero, features, how it works, technology, footer with disclaimer.
- `/assistant` — chat: English / ಕನ್ನಡ / हिन्दी answers, voice questions, verified citations, backend status.

## API calls (`src/lib/api.ts`)

| Endpoint | Used for |
|---|---|
| `GET /api/health` | Connection indicator (polled every 15 s) |
| `GET /api/status` | Indexed documents, model, whether voice input is configured |
| `POST /api/chat` | Typed questions: `{ question, language, history }` |
| `POST /api/voice-chat` | Voice questions: form data with `file`, `language` and repeated `history` |
| `POST /api/speech-to-text` | Available in the client (`speechToText`); the chat uses `/api/voice-chat` |

`language` is always one of `english`, `kannada` or `hindi`.

## Voice input

The microphone button records with the browser's `MediaRecorder` (WebM/Opus in Chrome, Edge and Firefox; MP4 in Safari) for up to 29 seconds and sends the audio to `/api/voice-chat`. Browsers only allow the microphone on `localhost` or HTTPS pages.

## Structure

```
src/
  main.tsx, App.tsx            Entry point and routes
  index.css                    Tailwind theme (BIS blue) and shared classes
  lib/api.ts                   Typed FastAPI client and error handling
  lib/languages.ts             The three supported languages
  hooks/backendStatus.tsx      Connection polling shared by all pages
  hooks/useRecorder.ts         Microphone recording
  components/                  Navbar, footer, logo, status indicator, hero illustration
  components/chat/             Message bubbles, answer formatting, citations, composer, language selector
  pages/                       Landing, Assistant, NotFound
```
