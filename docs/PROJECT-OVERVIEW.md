# Project Overview

A plain-language summary of the AI Teaching Platform — what it is, why it
exists, what's built, and where it's going. (Technical detail lives in
`README.md`, `API.md` and `DECISIONS.md`.)

---

## The idea in one paragraph

Most AI tools (like ChatGPT) don't know a school's own textbooks. This platform
lets a school or teacher **upload their textbooks**, and then ask questions,
generate tests, worksheets, notes and lesson plans **strictly from those
books**. Answers are grounded in the actual curriculum, not the open internet.

---

## The problem

- Teachers spend hours preparing lesson plans, worksheets, question papers,
  notes and presentations.
- Students re-read 600-page textbooks to find one topic.
- Generic AI gives generic answers because it doesn't know the school's books.

---

## The solution

Upload a book → the platform builds an AI knowledge base from it → teachers and
students get accurate, curriculum-aligned help instantly.

```
Upload book  →  index it once  →  ask / generate anything, grounded in the book
```

---

## What's built (working today)

| Area | Status |
|---|---|
| Upload any PDF, any size (tested 160 MB) | ✅ |
| Chapter detection & navigation | ✅ |
| Chat with book (streaming, markdown) | ✅ |
| Chat history (ChatGPT-style sidebar) | ✅ |
| Answer cache — repeats cost ₹0 | ✅ |
| Test-paper generator (print-ready PDF) | ✅ |
| Worksheet / notes / summary / flashcards / lesson plan | ✅ |
| Multi-key LLM failover | ✅ |
| Google Drive storage (no size limit) | ✅ |
| Cloud auto-processing worker | ✅ |
| Voice (Indian languages) | ⏳ planned |

---

## How it works (non-technical)

1. **Upload** — the PDF goes straight to secure cloud storage (Google Drive).
2. **Index once** — the platform reads the book, splits it into small passages,
   and stores a mathematical "fingerprint" of each passage.
3. **Ask** — your question is matched against those fingerprints; only the most
   relevant passages are sent to the AI, with the surrounding context.
4. **Answer** — the AI replies using only the book, citing page numbers.
5. **Repeat questions are free** — stored answers are returned instantly.

---

## Why it's affordable (₹0 infrastructure for the prototype)

| Component | Choice | Cost |
|---|---|---|
| Hosting (frontend + backend) | Vercel free tier | ₹0 |
| Database | Supabase free tier | ₹0 |
| Book storage | Google Drive (existing quota) | ₹0 |
| Processing worker | GitHub Actions free tier | ₹0 |
| AI | Existing API access + caching | Pay only when needed |

**Cost controls:** answer caching (repeats = 0 tokens), retrieval (only
relevant passages reach the AI), index-once design, and usage logging to
measure real cost per request.

---

## Who it's for

- **Schools / coaching institutes** — a shared knowledge base from their books.
- **Teachers** — faster lesson plans, worksheets, tests and notes.
- **Students** — instant, book-grounded answers and study material.

---

## Roadmap

1. **Semantic answer cache** — match near-duplicate questions, not just exact.
2. **Voice mode** (Sarvam STT + TTS) — ask and hear answers in Indian languages.
3. **Usage dashboard** — show tokens, cost and cache savings.
4. **Portals** — student, teacher and school-admin views (roles already in the
   database).
5. **Subscriptions** — paid plans via Razorpay.
6. **Production storage** — move from Google Drive to object storage (R2/S3)
   when scale demands it.

---

## Success criteria

- ✅ A 100–500 MB book uploads successfully.
- ✅ Chapters are extracted and organised.
- ✅ Questions return answers grounded in the uploaded book (not the internet).
- ✅ The full PDF is **never** re-sent to the AI on each question.
- ✅ Text chat works end-to-end.
- ✅ Repeat questions cost nothing.
- ⏳ Voice input/output works through Sarvam.
- ✅ AI usage and estimated cost can be measured per request.
