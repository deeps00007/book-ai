from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.api.deps import get_current_user
from app.models import User, Book, Chapter, ChatSession, ChatMessage, BookChunk
from app.schemas import (
    UserCreate, UserLogin, TokenResponse, UserResponse,
    BookResponse, BookUploadResponse, ChapterResponse,
    ChatRequest, ChatResponse, ChatSessionResponse,
)
from app.services.upload_service import save_uploaded_file, process_book
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

@router.post("/books/upload", response_model=BookUploadResponse)
async def upload_book(
    file: UploadFile = File(...),
    title: str = Form(...),
    author: str = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    file_path = save_uploaded_file(content, file.filename)

    book = Book(
        user_id=user.id,
        title=title,
        author=author,
        file_path=file_path,
        file_size=len(content),
        status="processing",
    )
    db.add(book)
    await db.flush()
    await db.commit()

    try:
        result = await process_book(file_path, title)

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
        session = ChatSession(user_id=user.id, book_id=req.book_id)
        db.add(session)
        await db.flush()

    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at)
        .limit(20)
    )
    chat_history = [
        {"role": m.role, "content": m.content}
        for m in history_result.scalars().all()
    ]

    response = await ask_book(db, req.book_id, req.question, chat_history, chapter_id=req.chapter_id)

    user_msg = ChatMessage(session_id=session.id, role="user", content=req.question)
    assistant_msg = ChatMessage(
        session_id=session.id, role="assistant", content=response.content,
        sources={"chunks": response.sources}, provider=response.provider,
        model=response.model, tokens_used=response.tokens_used,
        response_time_ms=response.response_time_ms,
    )
    db.add_all([user_msg, assistant_msg])

    return ChatResponse(
        answer=response.content,
        session_id=session.id,
        sources=response.sources,
        provider=response.provider,
        model=response.model,
        tokens_used=response.tokens_used,
        response_time_ms=response.response_time_ms,
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
        session = ChatSession(user_id=user.id, book_id=req.book_id)
        db.add(session)
        await db.flush()

    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at)
        .limit(20)
    )
    chat_history = [
        {"role": m.role, "content": m.content}
        for m in history_result.scalars().all()
    ]

    user_msg = ChatMessage(session_id=session.id, role="user", content=req.question)
    db.add(user_msg)
    await db.commit()

    async def event_stream():
        full_response = ""
        sources = None
        try:
            async for chunk in ask_book_stream(db, req.book_id, req.question, chat_history, chapter_id=req.chapter_id):
                if chunk.get("__sources__"):
                    sources = chunk.get("sources")
                else:
                    full_response += chunk.get("content", "")
                    yield f"data: {json.dumps(chunk)}\n\n"
        finally:
            async with db.bind.begin() as conn:
                async_session = AsyncSession(conn)
                assistant_msg = ChatMessage(
                    session_id=session.id, role="assistant", content=full_response,
                    sources={"chunks": sources} if sources else None,
                    provider="fireworks", model="deepseek-v4-pro",
                )
                async_session.add(assistant_msg)
                await async_session.commit()

            done = {"done": True, "session_id": session.id, "sources": sources}
            yield f"data: {json.dumps(done)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
