# Engineering Decisions & Problem Log

A running record of the real problems encountered while building the platform
and the decision made for each — useful context for anyone maintaining it.

---

## 1. Serverless can't process large PDFs → background worker

**Problem.** Vercel serverless functions have a hard **60 s** limit. A 160 MB
PDF took > 3 minutes to process, so every large upload failed
(`FUNCTION_INVOCATION_TIMEOUT`).

**Decision.** Split responsibilities:
- **Web API** (Vercel): auth, retrieval, chat streaming, generation.
- **Worker** (any machine / GitHub Actions): heavy PDF processing, no timeout.

Books ≥ 5 MB are queued (`status=uploaded`) and picked up by the worker;
smaller books are processed inline.

---

## 2. PyMuPDF vs pypdf

**Problem.** `pypdf` is pure Python and slow (25 min for a 160 MB scanned
book). PyMuPDF is ~50× faster but its native libraries crash on Vercel's
sandbox.

**Decision.** Use **PyMuPDF in the worker** (Linux/macOS) and keep `pypdf` as
the Vercel fallback. `upload_service.py` detects which is available.

---

## 3. The expensive `get_text("dict")` call

**Problem.** Chapter detection called PyMuPDF's layout API
(`get_text("dict")`) **twice per page** to read font sizes. On a 240-page,
image-heavy PDF this alone took **~54 s**.

**Decision.** Detect chapters from the **already-extracted text** (regex on the
first lines of each page). Chapter detection went **54 s → 0 s**. Chunk
boundaries were also decoupled from chapter detection entirely (they now follow
page order), which fixed the "weird answers" bug (see #4).

---

## 4. "Weird answers" — broken chunking (the big one)

**Problem.** The chapter detector matched **any** occurrence of "Chapter X"
(table of contents, running headers, cross-references). It produced chapters in
the wrong order pointing at wrong pages:

```
1. p.11-11 "Chapter 10" ... 17. p.218-240 "Chapter 1"   ← Chapter 1 at the END
```

Books were chunked along these garbage boundaries, so retrieval returned
mismatched context.

**Decision.** **Chunk strictly in page order** (500 words, 80 overlap).
Chapter detection is now only a navigation label. Answer quality improved
immediately and verifiably.

---

## 5. RAG answered the *wrong* passage

**Problem.** "What did Lencho hope for?" returned *"he hoped for help from
God"* — a semantically similar phrase from **later** in the story — instead of
the correct *"he hoped for rain"*.

**Decision.** Build a richer pipeline:
1. **Question anchoring** — find the user's exact/near-exact question inside
   the book; when found, prioritise the surrounding chunks.
2. **Hybrid retrieval** — vector similarity + BM25 lexical score.
3. **Proximity boost** — chunks near the anchor rank higher.
4. **Labelled prompt** — `[LOCAL CONTEXT]` vs `[OTHER CONTEXT]`, plus a
   story-timeline instruction.
5. **Two-pass scoring** — vector filter first, then full scoring on the top 50
   for speed.

---

## 6. Supabase Storage 50 MB per-file limit

**Problem.** The free plan caps a single object at 50 MB; a 160 MB textbook was
rejected with `413`.

**Decision.** Store large books in **Google Drive**. Supabase keeps only
metadata and chunks.

---

## 7. Vercel 4.5 MB request-body limit

**Problem.** Uploading a large PDF to the API hit
`413 Content Too Large` (surfaced in the browser as a **CORS** error, because
the 413 page had no CORS headers).

**Decision.** Upload the PDF **directly from the browser to Google Drive**
(resumable), bypassing the API entirely.

---

## 8. Service accounts have no Google Drive quota

**Problem.** A Google *service account* cannot upload to a personal Drive:

> "Service Accounts do not have storage quota."

**Decision.** Use a **single platform Google account** with a stored **OAuth
refresh token**. Uploads use that account's quota; no per-user login, no
test-user limit.

---

## 9. Google Drive CORS on browser upload

**Problem.** The browser `PUT` to the resumable session was blocked by CORS
because the session was created without an `Origin` header.

**Decision.** The frontend sends `window.location.origin`; the backend forwards
it as the `Origin` header when creating the session. Google then returns the
correct CORS headers.

---

## 10. PgBouncer + asyncpg prepared-statement collisions

**Problem.** `DuplicatePreparedStatementError` on every query through Supabase's
pooler. Both `asyncpg` and later `psycopg3` used named prepared statements that
collided.

**Decision.** Switch to **`psycopg` v3** and disable prepared statements
(`connect_args`) / rely on `NullPool`. See `core/database.py`.

---

## 11. Secrets in git blocked the push

**Problem.** The backend entrypoint hard-coded the DB password, Google tokens
and API keys. GitHub's push protection rejected the push, and secrets sat in
history.

**Decision.** Move **all secrets to Vercel environment variables**. The
entrypoint (`api-deploy/api/index.py`) now contains only non-secret flags.
History was rewritten clean (single clean commit).

---

## 12. Env values corrupted to `value\r\nn`

**Problem.** Piping values into the Vercel CLI on Windows appended `\r\nn`
(CRLF + the answer to an interactive prompt), producing e.g.
`https://api.fireworks.ai/inference/v1\r\nn`, which crashed the app with
`InvalidURL: Invalid non-printable ASCII character`.

**Decision.** `config.py` sanitises **every** string setting: keep the first
line, strip CR/LF/whitespace. Belt-and-suspenders `.strip()` calls at the point
of use for URLs/keys.

---

## 13. Fireworks rotates and deprecates models

**Problem.** `deepseek-v4-pro` and later `deepseek-v4-pro-0813` started
returning `404 Model not found`.

**Decision.** Pin a currently-available model (`deepseek-v4p1-flash`) and keep
model selection in one place (`llm_gateway.py`). A model 404 must **not**
exhaust an API key — only auth/quota errors do (`is_key_exhausted_error`).

---

## 14. Per-user API keys broke new users

**Problem.** Keys were stored per user, so a new user had none and processing
fell back to a suspended default key.

**Decision.** Make the key pool **platform-wide** — one shared pool for all
users, always consulted.

---

## 15. Streaming broke with `ERR_INCOMPLETE_CHUNKED_ENCODING`

**Problem.** The SSE generator reused the request-scoped DB session, which is
already closed once the response starts.

**Decision.** Open a **fresh session inside the generator**, add SSE headers
(`Cache-Control: no-transform`, `X-Accel-Buffering: no`), and stream errors as
events instead of crashing the stream.

---

## 16. Slow processing (3× → 4× faster)

**Problem.** A large book took 193 s to process.

**Fixed by:**
- Removing the `get_text("dict")` layout calls (54 s saved).
- **Parallel** embedding batches (6 concurrent, batches of 10).
- Page-order chunking (instant).

Result: **193 s → 49 s** for a 160 MB book.

---

## 17. 10-minute "queuing" delay

**Problem.** The cloud worker ran on a **10-minute schedule**, so a fresh
upload waited for the next run.

**Decision.** The backend **triggers the GitHub Actions workflow instantly** on
upload (`github_trigger.py`), plus pip caching in the workflow. End-to-end
upload → ready is now ~70 s.

---

## 18. Chat UX & token spend → history + cache

**Problem.** No conversation history, and repeated questions re-billed the LLM.

**Decision.**
- ChatGPT-style **history sidebar** with auto-titled sessions.
- **Answer cache** (`answer_cache`): exact/normalised repeats return in ~5 s
  with **0 tokens**.
