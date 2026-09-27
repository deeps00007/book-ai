# AI Teaching Platform

A production-grade, RAG-powered AI learning platform for schools, teachers and
students. Upload textbooks, chat with them, generate tests / worksheets /
lesson plans, and more — grounded strictly in the uploaded books.

This document is the single source of truth for **what the platform is, how it
works, and how to run, deploy and maintain it**.

**Documentation set:**

| Document | Audience | Contents |
|---|---|---|
| `README.md` (this file) | Engineers | Architecture, setup, deployment, operations |
| `docs/API.md` | Engineers | Full API reference |
| `docs/DECISIONS.md` | Engineers | Problems hit and why each decision was made |
| `docs/PROJECT-OVERVIEW.md` | Stakeholders / clients | Plain-language summary, features, roadmap, costing |

---

## Table of contents

1. [What it does](#1-what-it-does)
2. [Live deployment](#2-live-deployment)
3. [Architecture](#3-architecture)
4. [Tech stack](#4-tech-stack)
5. [Repository layout](#5-repository-layout)
6. [Data model](#6-data-model)
7. [The RAG pipeline](#7-the-rag-pipeline)
8. [Book processing pipeline](#8-book-processing-pipeline)
9. [Storage strategy](#9-storage-strategy)
10. [LLM gateway & API key pool](#10-llm-gateway--api-key-pool)
11. [Chat, history & answer caching](#11-chat-history--answer-caching)
12. [Local development](#12-local-development)
13. [Deployment](#13-deployment)
14. [The background worker](#14-the-background-worker)
15. [Cost control](#15-cost-control)
16. [Known limits & roadmap](#16-known-limits--roadmap)

---

## 1. What it does

| Feature | Description |
|---|---|
| **Upload books** | Any PDF, any size (tested to 160 MB) |
| **Chapter detection** | Splits books into chapters for navigation |
| **Chat with book** | Context-grounded Q&A with streaming answers |
| **Chat history** | ChatGPT-style saved conversations |
| **Answer cache** | Repeat questions cost 0 tokens |
| **Test paper generator** | Professional black-and-white exam PDFs |
| **Worksheet / notes / summary / flashcards / lesson plan** | Auto-generated learning content |
| **Multi-key LLM pool** | Automatic failover across API keys |
| **Multi-language voice** | Planned (Sarvam STT + TTS) |

---

## 2. Live deployment

| Component | URL |
|---|---|
| **Frontend** | https://frontend-ten-orcin-456yf3zvl2.vercel.app |
| **Backend API** | https://bookai-api-three.vercel.app |
| **GitHub** | https://github.com/deeps00007/book-ai |

**Demo login:** `deepanshusingh036@gmail.com` / `demo1234`

---

## 3. Architecture

```
                    ┌──────────────────────────────┐
                    │   Next.js frontend (Vercel)  │
                    └───────────────┬──────────────┘
                                    │  REST + SSE
                    ┌───────────────▼──────────────┐
                    │   FastAPI backend (Vercel)    │
                    │  auth · books · chat · RAG    │
                    │  generate · test-paper · keys │
                    └───┬───────────┬───────────┬───┘
                        │           │           │
              ┌─────────▼──┐  ┌─────▼─────┐  ┌──▼─────────────┐
              │ Supabase   │  │ Google    │  │ LLM Gateway     │
              │ PostgreSQL │  │ Drive     │  │ Fireworks / etc │
              │ + pgvector │  │ (storage) │  │ + key pool      │
              └─────▲──────┘  └─────▲─────┘  └─────────────────┘
                    │               │
              ┌─────┴───────────────┴──────┐
              │  Background worker          │
              │  (local script / GitHub     │
              │   Actions, every few min)   │
              └─────────────────────────────┘
```

**Key idea:** serverless (Vercel) can't process a 160 MB PDF within its 60 s
limit, so heavy book processing is offloaded to a **worker**, while the web
API handles auth, retrieval, chat streaming and generation.

---

## 4. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 14 (App Router) + Tailwind | Fast, SSR, great DX |
| Backend | FastAPI (Python 3.12) | Async, typed, fast |
| Database | Supabase PostgreSQL + pgvector | Free, managed, vector-ready |
| Storage | Google Drive (platform account) | Free, no file-size limit |
| Embeddings | Fireworks `nomic-embed-text-v1.5` | Cheap, 768-dim |
| LLM | Fireworks (DeepSeek / GLM / Kimi) | Free tier + multi-provider pool |
| PDF parsing | PyMuPDF (worker) / pypdf (fallback) | PyMuPDF is ~50× faster |
| Async jobs | Celery + Redis (optional) / GitIA worker | Flexible |
| Hosting | Vercel (frontend + backend), GitHub Actions (worker) | Free |

---

## 5. Repository layout

```
book-ai/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── main.py           # app entrypoint, CORS, routers
│   │   ├── core/
│   │   │   ├── config.py     # settings (env + sanitisation)
│   │   │   ├── database.py   # async engine (SQLite / PostgreSQL)
│   │   │   └── security.py   # JWT + bcrypt
│   │   ├── api/
│   │   │   ├── deps.py       # current-user dependency
│   │   │   └── v1/
│   │   │       ├── router.py       # auth, books, chat, sessions
│   │   │       ├── generate.py     # worksheet / notes / etc.
│   │   │       ├── test_paper.py   # exam PDF generator
│   │   │       └── api_keys.py     # key pool management
│   │   ├── models/__init__.py      # all SQLAlchemy tables
│   │   ├── schemas/__init__.py     # Pydantic request/response models
│   │   └── services/
│   │       ├── llm_gateway.py      # multi-provider LLM + failover
│   │       ├── embedding_service.py# embeddings + key pool
│   │       ├── api_key_pool.py     # platform-wide key rotation
│   │       ├── rag_service.py      # retrieval + reranking + prompts
│   │       ├── upload_service.py   # PDF → chapters → chunks → embeddings
│   │       ├── google_drive_service.py # Drive upload/download
│   │       ├── github_trigger.py   # kick the worker instantly
│   │       ├── cache_service.py    # answer cache (0-token repeats)
│   │       ├── test_paper_service.py # PDF rendering (fpdf2)
│   │       └── storage_service.py  # Supabase storage helper
│   └── requirements.txt
│
├── frontend/                 # Next.js application
│   ├── src/app/
│   │   ├── login/            # auth
│   │   ├── dashboard/        # overview
│   │   ├── books/            # list, upload, chat
│   │   ├── generate/         # content generator
│   │   ├── test-paper/       # exam generator
│   │   └── api-keys/         # key pool UI
│   └── src/lib/
│       ├── api.ts            # API client
│       └── types.ts
│
├── api-deploy/               # Vercel Python serverless wrapper
│   ├── api/index.py          # entrypoint (reads env, imports app)
│   └── app/                  # copy of backend/app for deployment
│
├── worker.py                 # background book processor
├── start-worker.bat          # one-click worker launcher
├── seed_book.py              # local one-off book seeder
├── .github/workflows/
│   ├── process-books.yml     # cloud worker (every 10 min + on demand)
│   └── keep-alive.yml        # keeps Supabase from pausing
└── docker-compose.yml        # optional all-in-one local stack
```

---

## 6. Data model

| Table | Purpose |
|---|---|
| `users` | Accounts (teacher / student / admin) |
| `schools` | Multi-tenant organisation |
| `books` | Uploaded books (+ status, size, source path) |
| `chapters` | Detected chapters (navigation labels) |
| `book_chunks` | Text chunks + embeddings + page ranges |
| `chat_sessions` | A conversation (auto-titled) |
| `chat_messages` | Messages within a session (+ sources) |
| `answer_cache` | Cached Q→A (saves tokens on repeats) |
| `api_keys` | Platform-wide LLM key pool |
| `generated_content` | Worksheets / tests / notes output |
| `subscriptions` | Plans & credits |
| `api_usage_logs` | Per-request token/cost tracking |

**Book status lifecycle:** `uploading → uploaded → processing → ready | failed`

---

## 7. The RAG pipeline

The retrieval pipeline is deliberately more than "vector search":

```
User question
     │
     ▼
Embed query  ────────────────────────────────┐
     │                                        │
     ▼                                        │
Load chunks (book / chapter scoped)          │
     │                                        │
     ├─► Vector similarity (cosine)           │
     ├─► BM25 lexical score                   │
     └─► Question anchoring                   │
              (exact / fuzzy match of the    │
               question inside the book)      │
     │                                        │
     ▼                                        │
Hybrid score → proximity boost around anchor │
     │                                        │
     ▼                                        │
Cross-encoder rerank (qwen3-reranker-8b)      │
  · skipped when the question is anchored     │
  · scores the top ~12 candidates in ~1s      │
     │                                        │
     ▼                                        │
Build prompt with labelled context:          │
  [LOCAL CONTEXT]  (chunks near the question)│
  [OTHER CONTEXT]  (background)              │
     │                                        │
     ▼                                        ▼
LLM answer grounded in the local context
```

**Two-level answer cache** (checked before any LLM call):
- **exact** — normalised text match.
- **semantic** — embedding similarity ≥ 0.93, so paraphrases like
  *"What is an ecosystem?"* and *"define ecosystem"* share one answer.

Measured: a paraphrase returned in **8.8 s with 0 tokens** (vs a fresh
**~30 s / 5–7 k tokens** answer).

**Why it matters:** a naive RAG answers "What did Lencho hope for?" with
*"he hoped for help from God"* (a similar phrase later in the story). Our
pipeline anchors on the **question's location** and prioritises the
surrounding narrative, giving the correct *"he hoped for rain"*.

Files: `backend/app/services/rag_service.py`

---

## 8. Book processing pipeline

```
Upload (browser)
   │
   ├─ small (<5 MB) ──────────► processed inline by the backend
   │
   └─ large (≥5 MB) ──► Google Drive ──► queued ("uploaded")
                                              │
                                              ▼
                                    Background worker picks it up
                                              │
        ┌─────────────────────────────────────┘
        ▼
  download PDF ─► extract text (PyMuPDF)
        │
        ▼
  detect chapters (fast, text-based)
        │
        ▼
  chunk in page order (500 words, 80 overlap)
        │
        ▼
  embed in parallel batches (6 concurrent)
        │
        ▼
  store chunks + embeddings + page ranges
        │
        ▼
  status = "ready"
```

**Performance (160 MB, 240-page book):** ~49 s processing + ~37 s download.

**Optimisations applied:** dropped the expensive PyMuPDF `get_text("dict")`
layout API (was ~54 s), parallel embeddings, page-order chunking.

Files: `backend/app/services/upload_service.py`, `worker.py`

---

## 9. Storage strategy

| Concern | Solution |
|---|---|
| Supabase Storage 50 MB per-file limit | Store books in **Google Drive** instead |
| Vercel 4.5 MB request-body limit | Browser uploads **directly to Drive** (resumable) |
| Service accounts have no Drive quota | Use a **platform Google account** (OAuth refresh token) |
| Google CORS on upload | Backend passes the browser `Origin` when creating the session |
| Large-file timeout | Worker downloads once, processes, indexes |

**Flow:** backend creates a resumable Drive session → the browser `PUT`s the
file straight to Drive → the backend stores the `drive:<file_id>` and queues
processing. The PDF is downloaded **once** for indexing; questions never touch
the PDF again (only chunks + embeddings).

Files: `backend/app/services/google_drive_service.py`

---

## 10. LLM gateway & API key pool

`llm_gateway.py` presents **one interface** to many providers (Fireworks,
OpenAI, Groq) so the model can be swapped without code changes.

`api_key_pool.py` stores **multiple Fireworks keys** in the database:

- **Platform-wide** — one pool for all users (not per-user).
- Tried in order of fewest errors.
- A key is marked `exhausted` **only** on auth errors (401/403/412 / suspended
  / quota) — never on transient or model errors.
- The management UI lives at `/api-keys`.

---

## 11. Chat, history & answer caching

- **Sessions** are auto-titled from the first question.
- **Messages** persist and reload; the sidebar lists past chats.
- **Answer cache** (`answer_cache`): normalised question + book → answer.
  A repeat question returns instantly with **0 LLM tokens**.

| Ask | Time | Provider | Tokens |
|---|---|---|---|
| First time | ~17 s | fireworks | 5,874 |
| Repeat | ~5 s | **cache** | **0** |

Endpoints: `POST /chat`, `POST /chat/stream`,
`GET /chat/sessions/{book_id}`, `GET /chat/sessions/{id}/messages`,
`PATCH /chat/sessions/{id}`, `DELETE /chat/sessions/{id}`.

---

## 12. Local development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Uses SQLite by default (`USE_SQLITE=true` in `backend/.env`).

### Frontend

```bash
cd frontend
npm install
# frontend/.env.local
#   NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
npm run dev            # http://localhost:3000
```

### Worker (for books > 5 MB)

```bash
start-worker.bat       # or:  python worker.py
```

### Seeding a book without the UI

```bash
python seed_book.py "book.pdf" "Book Title" "Author"
```

---

## 13. Deployment

### Frontend → Vercel

Root: `frontend` · env `NEXT_PUBLIC_API_URL=https://bookai-api-three.vercel.app/api/v1`

### Backend → Vercel (Python serverless)

Root: `api-deploy` · entrypoint `api/index.py`

Environment variables (set in Vercel, **never committed**):

```
USE_SQLITE=false
ENVIRONMENT=production
DATABASE_URL=postgresql://...supabase...
SUPABASE_URL / SUPABASE_SERVICE_KEY
GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN
GOOGLE_DRIVE_FOLDER_ID
FIREWORKS_API_KEY
GITHUB_TOKEN / GITHUB_REPO   # to trigger the worker instantly
```

> **Gotcha handled:** env values piped on Windows can arrive as `value\r\nn`.
> `config.py` sanitises every string setting (keeps the first line only).

### Database → Supabase

Apply `setup.sql` (schema) and the `answer_cache` table via the SQL editor or
`supabase db push`.

---

## 14. The background worker

`worker.py` polls the database for books in `uploaded` / `processing` state and
processes them (any size).

Two ways to run it:

1. **Local** — `start-worker.bat` (instant, needs the window open).
2. **Cloud (free)** — GitHub Actions `.github/workflows/process-books.yml`,
   runs every 10 minutes **and** is triggered instantly by the backend on
   upload (via `github_trigger.py`).

Triggering instantly removed a 10-minute wait; end-to-end upload → ready is now
~70 s for a large book.

---

## Usage & cost dashboard

Every AI call is logged to `api_usage_logs` (provider, model, tokens in/out,
cost, latency, **cached** flag, book). The dashboard at `/usage` shows:

- **AI requests**, **cache hits** + hit-rate, **tokens**, **estimated cost**
  (USD + INR), **savings from caching**, **average response time**
- a **daily cost chart** and a **per-model breakdown**

Endpoints: `GET /usage/summary`, `GET /usage/daily`, `GET /usage/by-model`.

**What is tracked (and how accurate it is):**

| Data | Source | Accuracy |
|---|---|---|
| Requests, cache hits | counted | **exact** |
| Tokens in/out (chat, non-stream + stream) | provider `usage` (`stream_options.include_usage`) | **exact** |
| Embeddings | counted per batch (tokens ≈ chars/4) | token count **estimated**, request count exact |
| Rerank | counted per call (tokens ≈ chars/4) | token count **estimated**, request count exact |
| Generate / test-paper | provider `usage` | **exact** |
| Cost | `PRICES` table × tokens | **estimate**, not the provider's invoice |

**Cost is an estimate.** To make it exact, replace `PRICES` in
`backend/app/services/usage_service.py` with your real per-1M-token rates, or
reconcile totals against the provider's billing dashboard monthly.

## 15. Cost control

| Lever | Effect |
|---|---|
| Answer cache | Repeat questions = **0 tokens** |
| RAG (chunks, not full PDF) | Only relevant text reaches the LLM |
| Process once, index forever | The PDF is never re-sent |
| Key pool + failover | Never pay for a dead key |
| Cheap embedding model | Low embedding cost |
| GitHub Actions + Vercel + Supabase free tiers | **₹0 infrastructure** for the prototype |
| `api_usage_logs` | Per-request tokens, cost, latency, cache flag |

---

## 16. Known limits & roadmap

### Current limits

- **Exact** answer caching (not yet semantic / near-duplicate).
- Worker startup has ~30–50 s of GitHub Actions latency in the cloud path.
- Chapter labels are heuristic (chunking itself is page-order and correct).
- Voice (Sarvam) not yet implemented.

### Roadmap

1. **Semantic answer cache** — embed questions, match near-duplicates.
2. **Voice mode** — Sarvam STT + TTS for Indian languages.
3. **Usage dashboard** — surface `api_usage_logs` and cache savings.
4. **Student / Teacher / School portals** — roles already modelled.
5. **Subscription billing** — Razorpay integration (`subscriptions` table).

---

## Credits & conventions

- **Secrets** live only in environment variables — never in the repo.
- **Chunk boundaries** always follow page order; chapter detection is only for labels.
- **The LLM gateway** is the single place to add/remove providers.
- **The worker** is the only place that needs PyMuPDF.
