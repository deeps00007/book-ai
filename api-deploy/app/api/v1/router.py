from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import StreamingResponse
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
import json
import asyncio
import logging
from app.core.database import get_db, async_session

logger = logging.getLogger(__name__)
from app.core.security import hash_password, verify_password, create_access_token
from app.api.deps import get_current_user
from app.models import User, Book, Chapter, ChatSession, ChatMessage, BookChunk
from app.schemas import (
    UserCreate, UserLogin, TokenResponse, UserResponse,
    BookResponse, BookUploadResponse, ChapterResponse,
    ChatRequest, ChatResponse, ChatSessionResponse, ChatMessageResponse,
)
from app.services.upload_service import save_uploaded_file, process_book
from app.services.storage_service import upload_book_async
from app.services import google_drive_service
from app.services import github_trigger
from app.services import cache_service
from app.services import usage_service
from app.services.rag_service import ask_book, ask_book_stream

router = APIRouter()


# ── Auth ──

@router.post("/auth/register", response_model=TokenResponse)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        name=data.name,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.flush()

    token = create_access_token({"sub": user.id, "email": user.email})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": user.id, "email": user.email})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/auth/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


# ── Books ──

@router.get("/books/drive-status")
async def drive_status(user: User = Depends(get_current_user)):
    return {"configured": google_drive_service.is_configured()}


@router.post("/books/drive-session")
async def create_drive_session(
    req: dict = Body(...),
    user: User = Depends(get_current_user),
):
    """Create a Google Drive resumable upload session for large files."""
    if not google_drive_service.is_configured():
        raise HTTPException(status_code=503, detail="Google Drive is not configured")
    filename = req.get("filename", "book.pdf")
    mime = req.get("mime_type", "application/pdf")
    origin = req.get("origin") or None
    try:
        return await google_drive_service.create_resumable_upload_session(filename, mime, origin)
    except Exception as e:
        logger.error(f"Drive session error: {e}")
        raise HTTPException(status_code=500, detail=f"Drive session failed: {str(e)[:150]}")


async def _process_queued_book(db: AsyncSession, book: Book) -> BookUploadResponse:
    """Download (Drive or storage URLs), extract, chunk, embed, and mark ready.

    Shared by the upload endpoint, the manual process endpoint, and the worker.
    """
    # wipe stale data from any earlier attempt
    await db.execute(text("DELETE FROM book_chunks WHERE book_id = :b"), {"b": book.id})
    await db.execute(text("DELETE FROM chapters WHERE book_id = :b"), {"b": book.id})

    content = None
    err = None

    # Source 1: Google Drive ("drive:<file_id>")
    if book.file_path and book.file_path.startswith("drive:"):
        drive_file_id = book.file_path.split("drive:", 1)[1]
        try:
            content = await google_drive_service.download_file(drive_file_id)
        except Exception as e:
            err = f"Drive download failed: {str(e)[:150]}"

    # Source 2: stored chunk URLs in error_message JSON
    if content is None and not err and book.error_message and book.error_message.strip().startswith("{"):
        try:
            urls = json.loads(book.error_message).get("storage_urls", [])
        except Exception:
            urls = []
        if urls:
            parts = []
            try:
                if len(urls) == 1:
                    async with AsyncClient(timeout=120, follow_redirects=True) as c:
                        r = await c.get(urls[0]); r.raise_for_status(); parts = [r.content]
                else:
                    async def get(u):
                        async with AsyncClient(timeout=120, follow_redirects=True) as c:
                            r = await c.get(u); r.raise_for_status(); return r.content
                    res = await asyncio.gather(*[get(u) for u in urls], return_exceptions=True)
                    for i, r in enumerate(res):
                        if isinstance(r, Exception):
                            err = f"Part {i+1}: {type(r).__name__}"; break
                        parts.append(r)
            except Exception as e:
                err = str(e)[:150]
            if parts and not err:
                content = b"".join(parts)

    if content is None:
        book.status = "failed"
        book.error_message = err or "No source file found for this book"
        await db.commit()
        return BookUploadResponse(book_id=book.id, message=book.error_message, status="failed")

    book.status = "processing"
    await db.commit()

    fp = save_uploaded_file(content, f"book_{book.id[:8]}.pdf")

    try:
        result = await process_book(fp, book.title, user_id=book.user_id)
        cmap = {}
        for order, ci in enumerate(result.get("chapters", []), 1):
            ch = Chapter(book_id=book.id, title=ci["title"], order=order,
                         start_page=ci["start_page"], end_page=ci["end_page"])
            db.add(ch); await db.flush()
            cmap[ci["title"]] = ch.id
        for ck in result["chunks"]:
            db.add(BookChunk(
                book_id=book.id,
                chapter_id=cmap.get(ck.get("chapter", {}).get("title", "")),
                chunk_index=ck["index"], content=ck["text"],
                embedding_json=ck.get("embedding_json"),
                page_start=ck.get("page_start", 0),
                page_end=ck.get("page_end", 0),
            ))
        book.status = "ready"
        book.total_chunks = result["total_chunks"]
        book.total_pages = result["total_pages"]
        book.error_message = None
        await db.commit()
        return BookUploadResponse(
            book_id=book.id,
            message=f"Book processed: {len(result['chapters'])} chapters, {result['total_chunks']} chunks",
            status="ready",
        )
    except Exception as e:
        book.status = "failed"
        book.error_message = str(e)[:300]
        await db.commit()
        return BookUploadResponse(book_id=book.id, message=f"Processing failed: {str(e)[:150]}", status="failed")


@router.post("/books/upload-drive", response_model=BookUploadResponse)
async def upload_from_drive(
    req: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Process a book that was uploaded to Google Drive."""
    title = req.get("title", "")
    author = req.get("author") or None
    file_id = req.get("drive_file_id", "")
    file_size = req.get("file_size", 0)

    if not title or not file_id:
        raise HTTPException(status_code=400, detail="title and drive_file_id are required")

    if not user.school_id:
        pass  # single-user prototype, no school enforcement

    # Small files process inline (fast). Large files are queued for the worker.
    # Only trivially small files process inline (Vercel has a 60s limit).
    # Everything else is queued and picked up by the fast worker within ~30s.
    SMALL_FILE_LIMIT = 5 * 1024 * 1024

    book = Book(
        user_id=user.id, title=title, author=author,
        file_path=f"drive:{file_id}", file_size=file_size, status="uploaded",
    )
    db.add(book)
    await db.flush()
    await db.commit()

    if file_size and file_size > SMALL_FILE_LIMIT:
        # Too large to process within the serverless limit — leave queued for the worker,
        # and kick the GitHub Actions worker NOW instead of waiting for the schedule.
        await github_trigger.trigger_worker()
        return BookUploadResponse(
            book_id=book.id,
            message="Uploaded. Processing has started.",
            status="uploaded",
        )

    return await _process_queued_book(db, book)


@router.post("/books/upload", response_model=BookUploadResponse)
async def upload_book(
    req: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    title = req.get("title", "")
    author = req.get("author") or None
    storage_url = req.get("storage_url", "")
    storage_urls = req.get("storage_urls", [])
    file_size = req.get("file_size", 0)

    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    # Support single URL (small files) or multiple chunk URLs (large files)
    urls_to_download = storage_urls if storage_urls else ([storage_url] if storage_url else [])

    if not urls_to_download:
        raise HTTPException(status_code=400, detail="storage_url or storage_urls is required")

    is_chunked = len(urls_to_download) > 1

    if is_chunked:
        book = Book(user_id=user.id, title=title, author=author,
                     file_path=urls_to_download[0], file_size=file_size,
                     status="uploaded",
                     error_message=json.dumps({"storage_urls": urls_to_download}))
        db.add(book)
        await db.flush()
        await db.commit()
        return BookUploadResponse(
            book_id=book.id,
            message=f"Uploaded in {len(urls_to_download)} parts. Processing will start shortly.",
            status="uploading",
        )

    # Download all chunks in parallel
    content_parts = []
    download_error = None

    async def download_one(url):
        async with AsyncClient(timeout=120, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.content

    if len(urls_to_download) == 1:
        try:
            async with AsyncClient(timeout=120, follow_redirects=True) as http_client:
                dl = await http_client.get(urls_to_download[0])
                dl.raise_for_status()
                content_parts = [dl.content]
        except Exception as e:
            download_error = f"Download: {type(e).__name__}: {str(e)[:100]}"
    else:
        import asyncio as _asyncio
        try:
            results = await _asyncio.gather(*[download_one(u) for u in urls_to_download], return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    download_error = f"Part {i+1}: {type(r).__name__}: {str(r)[:100]}"
                    break
                content_parts.append(r)
        except Exception as e:
            download_error = f"Gather: {type(e).__name__}: {str(e)[:100]}"

    content = b"".join(content_parts) if content_parts else None
    file_path = None

    if content and len(content) > 0:
        file_path = save_uploaded_file(content, f"book_{len(content)}.pdf")

    book = Book(
        user_id=user.id,
        title=title,
        author=author,
        file_path=storage_url or (file_path or ""),
        file_size=file_size or len(content or b""),
        status="processing",
    )
    db.add(book)
    await db.flush()
    await db.commit()

    try:
        if not file_path:
            book.status = "failed"
            book.error_message = download_error or "Could not download PDF from storage"
            await db.commit()
            return BookUploadResponse(
                book_id=book.id,
                message=book.error_message,
                status="failed",
            )

        result = await process_book(file_path, title, user_id=user.id)

        chapter_map = {}
        chapter_order = 0
        for ch_info in result.get("chapters", []):
            chapter_order += 1
            chapter = Chapter(
                book_id=book.id,
                title=ch_info["title"],
                order=chapter_order,
                start_page=ch_info["start_page"],
                end_page=ch_info["end_page"],
            )
            db.add(chapter)
            await db.flush()
            chapter_map[ch_info["title"]] = chapter.id

        for chunk in result["chunks"]:
            ch_title = chunk.get("chapter", {}).get("title", "")
            bk = BookChunk(
                book_id=book.id,
                chapter_id=chapter_map.get(ch_title),
                chunk_index=chunk["index"],
                content=chunk["text"],
                embedding_json=chunk.get("embedding_json"),
            )
            db.add(bk)

        book.status = "ready"
        book.total_chunks = result["total_chunks"]
        book.total_pages = result["total_pages"]
        await db.commit()

        return BookUploadResponse(
            book_id=book.id,
            message=f"Book processed: {len(result['chapters'])} chapters, {result['total_chunks']} chunks, {result['total_pages']} pages",
            status="ready",
        )
    except Exception as e:
        book.status = "failed"
        book.error_message = str(e)
        await db.commit()

        return BookUploadResponse(
            book_id=book.id,
            message=f"Processing failed: {str(e)}",
            status="failed",
        )


@router.post("/books/{book_id}/process", response_model=BookUploadResponse)
async def process_book_endpoint(
    book_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = await db.get(Book, book_id)
    if not book or book.user_id != user.id:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status == "ready":
        return BookUploadResponse(book_id=book.id, message="Already ready", status="ready")

    # Clear any stale chunks from a previous failed attempt
    await db.execute(text("DELETE FROM book_chunks WHERE book_id = :bid"), {"bid": book.id})
    await db.execute(text("DELETE FROM chapters WHERE book_id = :bid"), {"bid": book.id})

    content = None
    err = None

    # Source 1: Google Drive (file_path = "drive:<id>")
    if book.file_path and book.file_path.startswith("drive:"):
        drive_file_id = book.file_path.split("drive:", 1)[1]
        try:
            content = await google_drive_service.download_file(drive_file_id)
        except Exception as e:
            err = f"Drive download failed: {str(e)[:150]}"

    # Source 2: stored chunk URLs (Supabase) kept in error_message JSON
    if content is None and not err and book.error_message:
        urls = []
        try:
            urls = json.loads(book.error_message).get("storage_urls", [])
        except Exception:
            urls = []
        if urls:
            parts = []
            async def get(url):
                async with AsyncClient(timeout=120, follow_redirects=True) as c:
                    r = await c.get(url)
                    r.raise_for_status()
                    return r.content
            try:
                if len(urls) == 1:
                    async with AsyncClient(timeout=120, follow_redirects=True) as c:
                        r = await c.get(urls[0]); r.raise_for_status(); parts = [r.content]
                else:
                    res = await asyncio.gather(*[get(u) for u in urls], return_exceptions=True)
                    for i, r in enumerate(res):
                        if isinstance(r, Exception):
                            err = f"Part {i+1}: {type(r).__name__}"; break
                        parts.append(r)
            except Exception as e:
                err = str(e)[:150]
            if parts and not err:
                content = b"".join(parts)

    if content is None:
        book.status = "failed"
        book.error_message = err or "No source file found for this book"
        await db.commit()
        return BookUploadResponse(book_id=book.id, message=book.error_message, status="failed")

    book.status = "processing"
    await db.commit()

    fp = save_uploaded_file(content, f"book_{book.id[:8]}.pdf")

    try:
        result = await process_book(fp, book.title, user_id=user.id)

        chapter_map = {}
        for order, ci in enumerate(result.get("chapters", []), 1):
            ch = Chapter(book_id=book.id, title=ci["title"], order=order,
                         start_page=ci["start_page"], end_page=ci["end_page"])
            db.add(ch)
            await db.flush()
            chapter_map[ci["title"]] = ch.id

        for ck in result["chunks"]:
            db.add(BookChunk(
                book_id=book.id,
                chapter_id=chapter_map.get(ck.get("chapter", {}).get("title", "")),
                chunk_index=ck["index"], content=ck["text"],
                embedding_json=ck.get("embedding_json"),
                page_start=ck.get("page_start", 0),
                page_end=ck.get("page_end", 0),
            ))

        book.status = "ready"
        book.total_chunks = result["total_chunks"]
        book.total_pages = result["total_pages"]
        book.error_message = None
        await db.commit()
        return BookUploadResponse(book_id=book.id,
            message=f"Done: {len(result['chapters'])} chapters, {result['total_chunks']} chunks",
            status="ready")
    except Exception as e:
        book.status = "failed"
        book.error_message = str(e)[:300]
        await db.commit()
        return BookUploadResponse(book_id=book.id, message=f"Failed: {str(e)[:150]}", status="failed")


@router.get("/books", response_model=list[BookResponse])
async def list_books(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Book).where(Book.user_id == user.id).order_by(Book.created_at.desc())
    )
    books = result.scalars().all()
    return [BookResponse.model_validate(b) for b in books]


@router.get("/books/{book_id}", response_model=BookResponse)
async def get_book(
    book_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user.id)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return BookResponse.model_validate(book)


@router.get("/books/{book_id}/chapters", response_model=list[ChapterResponse])
async def get_chapters(
    book_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = await db.get(Book, book_id)
    if not book or book.user_id != user.id:
        raise HTTPException(status_code=404, detail="Book not found")

    result = await db.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.order)
    )
    return [ChapterResponse.model_validate(c) for c in result.scalars().all()]


# ── Chat ──

@router.post("/chat", response_model=ChatResponse)
async def chat_with_book(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = await db.get(Book, req.book_id)
    if not book or book.user_id != user.id:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status != "ready":
        raise HTTPException(status_code=400, detail="Book is still processing")

    if req.session_id:
        session = await db.get(ChatSession, req.session_id)
        if not session or session.user_id != user.id:
            raise HTTPException(status_code=404, detail="Chat session not found")
    else:
        session = ChatSession(user_id=user.id, book_id=req.book_id,
                              title=req.question[:60] or "New Chat")
        db.add(session)
        await db.flush()

    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at)
        .limit(20)
    )
    prior = history_result.scalars().all()
    chat_history = [{"role": m.role, "content": m.content} for m in prior]

    if not prior and (not session.title or session.title == "New Chat"):
        session.title = req.question[:60]

    import time as _t
    _t0 = _t.time()
    cached = await cache_service.get_cached(db, req.book_id, req.question, req.chapter_id)
    _t1 = _t.time()

    # Compute the query embedding ONCE and reuse it for both the semantic
    # cache check and retrieval (avoids a duplicate embedding call).
    q_emb = None
    if not cached:
        from app.services.embedding_service import create_embedding
        try:
            q_emb = await create_embedding(req.question, user.id, endpoint="embedding:query")
            cached = await cache_service.get_cached_semantic(
                db, req.book_id, req.question, user.id, query_embedding=q_emb)
        except Exception:
            q_emb = None
    _t2 = _t.time()

    tokens_in = tokens_out = 0
    if cached:
        answer, sources, provider, model, tokens, ms = (
            cached["answer"], cached["sources"], "cache", "cache", 0, 0
        )
    else:
        response = await ask_book(db, req.book_id, req.question, chat_history,
                                  chapter_id=req.chapter_id, user_id=user.id,
                                  query_embedding=q_emb, book_title=book.title)
        answer, sources, provider, model = (
            response.content, response.sources, response.provider, response.model
        )
        tokens, ms = response.tokens_used, response.response_time_ms
        tokens_in, tokens_out = response.tokens_in, response.tokens_out
        await cache_service.store_cached(db, req.book_id, req.question, answer,
                                         sources, req.chapter_id, user.id,
                                         query_embedding=q_emb)
    logger.info(f"[chat] cache exact={(_t1-_t0)*1000:.0f}ms semantic={(_t2-_t1)*1000:.0f}ms answer={(_t.time()-_t2)*1000:.0f}ms")

    db.add_all([
        ChatMessage(session_id=session.id, role="user", content=req.question),
        ChatMessage(session_id=session.id, role="assistant", content=answer,
                    sources={"chunks": sources} if sources else None,
                    provider=provider, model=model, tokens_used=tokens,
                    response_time_ms=ms),
    ])
    await db.commit()

    await usage_service.log_usage(
        db, user.id, provider, model, "/chat",
        tokens_in=tokens_in, tokens_out=tokens_out, response_time_ms=ms,
        cached=(provider in ("cache", "cache-semantic")), book_id=req.book_id,
    )

    return ChatResponse(
        answer=answer, session_id=session.id, sources=sources,
        provider=provider, model=model, tokens_used=tokens, response_time_ms=ms,
    )


@router.post("/chat/stream")
async def chat_with_book_stream(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = await db.get(Book, req.book_id)
    if not book or book.user_id != user.id:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status != "ready":
        raise HTTPException(status_code=400, detail="Book is still processing")

    if req.session_id:
        session = await db.get(ChatSession, req.session_id)
        if not session or session.user_id != user.id:
            raise HTTPException(status_code=404, detail="Chat session not found")
    else:
        session = ChatSession(user_id=user.id, book_id=req.book_id,
                              title=req.question[:60] or "New Chat")
        db.add(session)
        await db.flush()

    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at)
        .limit(20)
    )
    prior = history_result.scalars().all()
    chat_history = [{"role": m.role, "content": m.content} for m in prior]

    if not prior and (not session.title or session.title == "New Chat"):
        session.title = req.question[:60]

    # Cache check — if we already answered this, stream it back instantly (0 tokens)
    cached = await cache_service.get_cached(db, req.book_id, req.question, req.chapter_id)
    q_emb = None
    if not cached:
        from app.services.embedding_service import create_embedding
        try:
            q_emb = await create_embedding(req.question, user.id, endpoint="embedding:query")
            cached = await cache_service.get_cached_semantic(
                db, req.book_id, req.question, user.id, query_embedding=q_emb)
        except Exception:
            q_emb = None

    db.add(ChatMessage(session_id=session.id, role="user", content=req.question))
    await db.commit()

    session_id = session.id
    book_id = req.book_id
    question = req.question
    chapter_id = req.chapter_id
    user_id = user.id
    history_snapshot = list(chat_history)
    query_embedding = q_emb
    book_title_snapshot = book.title

    async def event_stream():
        full_response = ""
        sources = None

        # Cached answer: emit instantly
        if cached:
            full_response = cached["answer"]
            sources = cached["sources"]
            for i in range(0, len(full_response), 60):
                yield f"data: {json.dumps({'content': full_response[i:i+60], 'provider': 'cache'})}\n\n"
            async with async_session() as sdb:
                sdb.add(ChatMessage(session_id=session_id, role="assistant",
                                    content=full_response,
                                    sources={"chunks": sources} if sources else None,
                                    provider="cache", model="cache"))
                await sdb.commit()
                await usage_service.log_usage(
                    sdb, user_id, "cache", "cache", "/chat/stream",
                    cached=True, book_id=book_id,
                )
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'sources': sources, 'cached': True})}\n\n"
            return

        usage_info = None
        try:
            async with async_session() as stream_db:
                async for chunk in ask_book_stream(
                    stream_db, book_id, question, history_snapshot,
                    chapter_id=chapter_id, user_id=user_id,
                    query_embedding=query_embedding, book_title=book_title_snapshot,
                ):
                    if chunk.get("__sources__"):
                        sources = chunk.get("sources")
                    elif chunk.get("__usage__"):
                        usage_info = chunk.get("__usage__")
                    else:
                        full_response += chunk.get("content", "")
                        yield f"data: {json.dumps(chunk)}\n\n"

                stream_db.add(ChatMessage(
                    session_id=session_id, role="assistant", content=full_response,
                    sources={"chunks": sources} if sources else None,
                    provider="fireworks", model="minimax-m3",
                ))
                await stream_db.commit()

                await usage_service.log_usage(
                    stream_db, user_id,
                    (usage_info or {}).get("provider", "fireworks"),
                    (usage_info or {}).get("model", "minimax-m3"),
                    "/chat/stream",
                    tokens_in=(usage_info or {}).get("tokens_in", 0),
                    tokens_out=(usage_info or {}).get("tokens_out", len(full_response) // 4),
                    book_id=book_id,
                )

            await cache_service.store_cached(db, book_id, question, full_response,
                                             sources, chapter_id, user_id,
                                             query_embedding=query_embedding)
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'sources': sources})}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'error': f'Error: {str(e)[:150]}', 'done': True, 'session_id': session_id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Chat Sessions ──

@router.get("/chat/sessions/{book_id}", response_model=list[ChatSessionResponse])
async def list_sessions(
    book_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id, ChatSession.book_id == book_id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    return [ChatSessionResponse.model_validate(s) for s in sessions]



@router.get("/chat/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return [ChatMessageResponse.model_validate(m) for m in result.scalars().all()]


@router.patch("/chat/sessions/{session_id}")
async def rename_session(
    session_id: str,
    req: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    title = (req.get("title") or "").strip()
    if title:
        session.title = title[:200]
        await db.commit()
    return {"ok": True, "title": session.title}


@router.delete("/chat/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    await db.execute(text("DELETE FROM chat_messages WHERE session_id = :s"), {"s": session_id})
    await db.execute(text("DELETE FROM chat_sessions WHERE id = :s"), {"s": session_id})
    await db.commit()
    return {"ok": True}

