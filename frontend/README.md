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
- `/login` — sign in with a mobile number and a one-time code, with a Gmail address, or as a guest.
- `/assistant` — chat: English / ಕನ್ನಡ / हिन्दी answers, voice questions, verified citations, backend status. Needs a session; visitors without one are sent to `/login` and returned here afterwards.

## Sign-in (demo only)

Sign-in is handled entirely in the browser (`src/hooks/auth.tsx`). There is no auth backend, no password, and the API stays open to everyone.

- **Phone** — the number must be a 10-digit Indian mobile number. No SMS is sent: the one-time code is generated in the page, shown on screen, and expires after 120 seconds.
- **Gmail** — the address must end in `@gmail.com`. Google is not contacted. The name in the header is derived from the address.
- **Guest** — one click, no details, and exactly the same access as a signed-in user.

The session is stored in `localStorage` under `bis-assistant.session`, so it survives a reload and ends on **Sign out** in the header menu. It is identity for display only: do not treat it as access control. To make it real, replace `signInWithPhone` and `signInWithGoogle` in `src/hooks/auth.tsx` with backend calls and keep the rest of the context unchanged.

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
  hooks/auth.tsx               Sign-in state kept in localStorage (phone, Gmail or guest)
  hooks/backendStatus.tsx      Connection polling shared by all pages
  hooks/useRecorder.ts         Microphone recording
  components/                  Navbar, footer, logo, status indicator, hero illustration, user menu, route guard
  components/chat/             Message bubbles, answer formatting, citations, composer, language selector
  pages/                       Landing, Login, Assistant, NotFound
```
