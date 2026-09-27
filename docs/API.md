# API Reference

Base URL (production): `https://bookai-api-three.vercel.app/api/v1`
Base URL (local): `http://localhost:8000/api/v1`

All authenticated endpoints require:

```
Authorization: Bearer <access_token>
```

---

## Auth

### `POST /auth/register`
```json
{ "email": "teacher@school.edu", "name": "Mr Sharma", "password": "secret123", "role": "teacher" }
```
→ `{ "access_token": "...", "token_type": "bearer", "user": { ... } }`

### `POST /auth/login`
```json
{ "email": "teacher@school.edu", "password": "secret123" }
```
→ `TokenResponse`

### `GET /auth/me`
→ `UserResponse`

---

## Books

### `POST /books/drive-session`
Creates a Google Drive resumable upload session.

```json
{ "filename": "biology.pdf", "mime_type": "application/pdf", "origin": "https://app.example.com" }
```
→ `{ "upload_url": "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=..." }`

The client then `PUT`s the file bytes to `upload_url` and reads the returned
file `id`.

### `POST /books/upload-drive`
Registers an uploaded Drive file and (for large files) queues processing.

```json
{ "title": "Biology", "author": "NCERT", "drive_file_id": "1eMD6...", "file_size": 167493608 }
```
→ `{ "book_id": "...", "message": "Uploaded. Processing has started.", "status": "uploaded" }`

### `POST /books/upload`
Legacy / small-file upload via storage URLs.

```json
{ "title": "Biology", "storage_url": "https://...", "storage_urls": ["...", "..."], "file_size": 123 }
```

### `GET /books/drive-status`
→ `{ "configured": true }`

### `GET /books`
→ `[ BookResponse, ... ]`

### `GET /books/{book_id}`
→ `BookResponse`

### `GET /books/{book_id}/chapters`
→ `[ ChapterResponse, ... ]`

### `POST /books/{book_id}/process`
Re-processes a queued/failed book.
→ `BookUploadResponse`

**BookResponse**
```json
{
  "id": "uuid", "title": "Biology", "author": "NCERT",
  "total_pages": 240, "total_chunks": 138,
  "status": "ready", "created_at": "2026-09-26T..."
}
```

Book status values: `uploading`, `uploaded`, `processing`, `ready`, `failed`.

---

## Chat

### `POST /chat`
Non-streaming answer.

```json
{ "book_id": "uuid", "question": "What is an ecosystem?", "session_id": "uuid|null", "chapter_id": "uuid|null" }
```
→
```json
{
  "answer": "An ecosystem is ...",
  "session_id": "uuid",
  "sources": [ { "content": "...", "page_start": 218, "page_end": 220 } ],
  "provider": "fireworks",
  "model": "accounts/fireworks/models/deepseek-v4p1-flash",
  "tokens_used": 5874,
  "response_time_ms": 17120
}
```
`provider` is `"cache"` when the answer came from the answer cache (0 tokens).

### `POST /chat/stream`
Server-Sent Events. Same body as `/chat`.

Each line:
```
data: {"content": "...", "provider": "fireworks", "model": "..."}
data: {"done": true, "session_id": "...", "sources": [ ... ]}
```
Cached answers include `"cached": true`. Errors stream as
`data: {"error": "...", "done": true}`.

### `GET /chat/sessions/{book_id}`
→ `[ ChatSessionResponse, ... ]`

### `GET /chat/sessions/{session_id}/messages`
→ `[ ChatMessageResponse, ... ]`

### `PATCH /chat/sessions/{session_id}`
```json
{ "title": "Photosynthesis doubts" }
```
→ `{ "ok": true, "title": "..." }`

### `DELETE /chat/sessions/{session_id}`
→ `{ "ok": true }`

---

## Generation

### `POST /generate`
```json
{
  "book_id": "uuid",
  "content_type": "worksheet | lesson_plan | notes | summary | flashcards",
  "topic": "Photosynthesis",
  "grade_level": "Grade 10",
  "additional_instructions": "...",
  "chapter_id": "uuid|null"
}
```
→ `{ "content_id": "...", "content_type": "worksheet", "title": "...", "content": { ... } }`

### `POST /test-paper`
Returns a **PDF** (`application/pdf`, attachment).

```json
{
  "book_id": "uuid",
  "chapter_ids": ["uuid", "uuid"],
  "school_name": "Delhi Public School",
  "class_name": "10th Grade",
  "subject": "Science",
  "duration": "2 hours",
  "topic": "Ecosystem",
  "question_types": [
    { "type": "mcq", "label": "MCQ", "count": 5, "marks_per": 2 },
    { "type": "short_answer", "label": "Answer the following", "count": 5, "marks_per": 3 }
  ]
}
```

---

## API Key Pool

### `POST /api-keys`
```json
{ "api_key": "fw_...", "label": "Account 2", "provider": "fireworks" }
```

### `GET /api-keys`
→ `{ "keys": [ { "id", "label", "provider", "status", "error_count", "last_error", "last_used" } ], "active_count": 2 }`

### `DELETE /api-keys/{key_id}`
→ `{ "ok": true }`

Key status: `active` | `exhausted`.

---

## Health

### `GET /health`  (root, not `/api/v1`)
→ `{ "status": "ok", "version": "1.0.0" }`

### `GET /dbcheck`  (root)
→ `{ "configured": true, "db": "ok" }`
