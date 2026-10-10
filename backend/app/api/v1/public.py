"""Public, no-auth endpoints for the standalone Test Paper app.

These reuse the same books/chapters/chunks tables and processing pipeline as the
main app, but every book is owned by a single shared "public" user so no login is
required. Only upload + chapter listing + test-paper generation are exposed.
"""

import re
import logging
from typing import Optional
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, async_session
from app.models import User, Book, Chapter
from app.api.v1.router import _process_queued_book
from app.services import github_trigger, google_drive_service
from app.services.test_paper_service import (
    generate_test_paper_questions, build_test_paper_pdf,
)

logger = logging.getLogger(__name__)
router = APIRouter()

PUBLIC_EMAIL = "public@testpaper.local"
SMALL_FILE_LIMIT = 5 * 1024 * 1024

# Question types a paper can be built from (used by the UI picker).
QUESTION_TYPE_CATALOG = [
    {"type": "mcq", "label": "Multiple Choice Questions", "marks_per": 1},
    {"type": "fill_blank", "label": "Fill in the Blanks", "marks_per": 1},
    {"type": "true_false", "label": "True / False", "marks_per": 1},
    {"type": "match", "label": "Match the Following", "marks_per": 1},
    {"type": "assertion_reason", "label": "Assertion-Reason", "marks_per": 1},
    {"type": "very_short", "label": "Very Short Answer Questions", "marks_per": 1},
    {"type": "short_answer", "label": "Short Answer Questions", "marks_per": 2},
    {"type": "long_answer", "label": "Long Answer Questions", "marks_per": 5},
    {"type": "case_study", "label": "Case Study / Source Based", "marks_per": 4},
]


async def _get_public_user(db: AsyncSession) -> User:
    r = await db.execute(select(User).where(User.email == PUBLIC_EMAIL))
    user = r.scalar_one_or_none()
    if not user:
        user = User(email=PUBLIC_EMAIL, name="Public User",
                    hashed_password="!", role="public")
        db.add(user)
        await db.flush()
        await db.commit()
    return user


def _grade(class_name: str) -> int:
    m = re.search(r"(\d{1,2})", class_name or "")
    return int(m.group(1)) if m else 8


def _difficulty_and_structure(class_name: str):
    """Difficulty + question mix derived from the class standard."""
    g = _grade(class_name)
    if g <= 5:
        difficulty = ("easy — simple, direct, fact-based questions with short sentences "
                      "and everyday examples from the book")
        structure = [
            {"type": "mcq", "label": "Multiple Choice Questions", "count": 8, "marks_per": 1},
            {"type": "fill_blank", "label": "Fill in the Blanks", "count": 5, "marks_per": 1},
            {"type": "short_answer", "label": "Short Answer Questions", "count": 4, "marks_per": 2},
        ]
    elif g <= 8:
        difficulty = ("medium — a mix of recall and understanding, with some questions "
                      "asking students to explain in their own words or apply concepts")
        structure = [
            {"type": "mcq", "label": "Multiple Choice Questions", "count": 8, "marks_per": 1},
            {"type": "short_answer", "label": "Short Answer Questions", "count": 5, "marks_per": 2},
            {"type": "long_answer", "label": "Long Answer Questions", "count": 3, "marks_per": 4},
        ]
    elif g <= 10:
        difficulty = ("hard — application and reasoning questions requiring structured, "
                      "justified answers and at least one higher-order thinking question")
        structure = [
            {"type": "mcq", "label": "Multiple Choice Questions", "count": 10, "marks_per": 1},
            {"type": "short_answer", "label": "Short Answer Questions", "count": 5, "marks_per": 2},
            {"type": "long_answer", "label": "Long Answer Questions", "count": 4, "marks_per": 5},
        ]
    else:
        difficulty = ("advanced — analytical and application questions requiring detailed "
                      "explanations, reasoning and multi-step answers for senior secondary level")
        structure = [
            {"type": "mcq", "label": "Multiple Choice Questions", "count": 10, "marks_per": 1},
            {"type": "short_answer", "label": "Short Answer Questions", "count": 5, "marks_per": 2},
            {"type": "long_answer", "label": "Long Answer Questions", "count": 5, "marks_per": 5},
        ]
    return difficulty, structure


# ── Books ──

@router.get("/public/books")
async def public_list_books():
    async with async_session() as db:
        user = await _get_public_user(db)
        books = (await db.execute(
            select(Book).where(Book.user_id == user.id).order_by(Book.created_at.desc())
        )).scalars().all()
        return [{
            "id": b.id, "title": b.title, "author": b.author,
            "status": b.status, "total_pages": b.total_pages,
            "total_chunks": b.total_chunks, "error_message": b.error_message,
        } for b in books]


@router.get("/public/books/{book_id}")
async def public_get_book(book_id: str):
    async with async_session() as db:
        user = await _get_public_user(db)
        book = await db.get(Book, book_id)
        if not book or book.user_id != user.id:
            raise HTTPException(status_code=404, detail="Book not found")
        chapters = (await db.execute(
            select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.order)
        )).scalars().all()
        return {
            "id": book.id, "title": book.title, "author": book.author,
            "status": book.status, "total_pages": book.total_pages,
            "total_chunks": book.total_chunks, "error_message": book.error_message,
            "chapters": [{
                "id": c.id, "title": c.title, "order": c.order,
                "start_page": c.start_page, "end_page": c.end_page,
            } for c in chapters],
        }


@router.post("/public/books/drive-session")
async def public_drive_session(req: dict = Body(...)):
    """Create a Google Drive resumable upload session (no auth)."""
    if not google_drive_service.is_configured():
        raise HTTPException(status_code=503, detail="Google Drive is not configured")
    try:
        return await google_drive_service.create_resumable_upload_session(
            req.get("filename", "book.pdf"),
            req.get("mime_type", "application/pdf"),
            req.get("origin") or None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drive session failed: {str(e)[:150]}")


@router.post("/public/books/upload-drive")
async def public_upload_drive(req: dict = Body(...)):
    title = (req.get("title") or "").strip()
    author = req.get("author") or None
    file_id = req.get("drive_file_id", "")
    file_size = req.get("file_size", 0)
    if not title or not file_id:
        raise HTTPException(status_code=400, detail="title and drive_file_id are required")

    async with async_session() as db:
        user = await _get_public_user(db)
        book = Book(user_id=user.id, title=title, author=author,
                    file_path=f"drive:{file_id}", file_size=file_size, status="uploaded")
        db.add(book)
        await db.flush()
        await db.commit()
        if file_size and file_size > SMALL_FILE_LIMIT:
            await github_trigger.trigger_worker()
            return {"book_id": book.id, "status": "uploaded",
                    "message": "Uploaded. Processing has started."}
        result = await _process_queued_book(db, book)
        return {"book_id": book.id, "status": result.status, "message": result.message}


@router.post("/public/books/upload")
async def public_upload_storage(req: dict = Body(...)):
    title = (req.get("title") or "").strip()
    author = req.get("author") or None
    storage_url = req.get("storage_url") or ""
    storage_urls = req.get("storage_urls") or []
    file_size = req.get("file_size", 0)
    if not title or not (storage_url or storage_urls):
        raise HTTPException(status_code=400, detail="title and file url are required")

    async with async_session() as db:
        user = await _get_public_user(db)
        book = Book(user_id=user.id, title=title, author=author,
                    file_path=storage_url or (storage_urls[0] if storage_urls else ""),
                    file_size=file_size, status="uploaded")
        db.add(book)
        await db.flush()
        # _process_queued_book reads stored URLs from error_message JSON
        if len(storage_urls) > 1:
            import json as _json
            book.error_message = _json.dumps({"storage_urls": storage_urls})
        await db.commit()
        result = await _process_queued_book(db, book)
        return {"book_id": book.id, "status": result.status, "message": result.message}


@router.post("/public/books/{book_id}/process")
async def public_process_book(book_id: str):
    async with async_session() as db:
        user = await _get_public_user(db)
        book = await db.get(Book, book_id)
        if not book or book.user_id != user.id:
            raise HTTPException(status_code=404, detail="Book not found")
        result = await _process_queued_book(db, book)
        return {"book_id": book.id, "status": result.status, "message": result.message}


@router.delete("/public/books/{book_id}")
async def public_delete_book(book_id: str):
    from sqlalchemy import text as _text
    async with async_session() as db:
        user = await _get_public_user(db)
        book = await db.get(Book, book_id)
        if not book or book.user_id != user.id:
            raise HTTPException(status_code=404, detail="Book not found")
        await db.execute(_text("DELETE FROM book_chunks WHERE book_id = :b"), {"b": book_id})
        await db.execute(_text("DELETE FROM chapters WHERE book_id = :b"), {"b": book_id})
        await db.delete(book)
        await db.commit()
        return {"deleted": book_id}


# ── Test Paper ──

@router.get("/public/test-paper/suggest")
async def public_test_paper_suggest(class_name: str = "Class 8"):
    """Auto-suggested difficulty + question mix for a class standard."""
    difficulty, structure = _difficulty_and_structure(class_name)
    return {
        "difficulty": difficulty,
        "question_types": structure,
        "total_marks": sum(q["count"] * q["marks_per"] for q in structure),
        "catalog": QUESTION_TYPE_CATALOG,
    }


def _clean_question_types(raw: list) -> list[dict]:
    out = []
    for q in raw or []:
        qtype = str(q.get("type") or "").strip()
        if not qtype:
            continue
        try:
            count = max(1, min(50, int(q.get("count", 1))))
            marks = max(1, min(20, int(q.get("marks_per", 1))))
        except (TypeError, ValueError):
            continue
        label = str(q.get("label") or qtype).strip()
        out.append({"type": qtype, "label": label, "count": count, "marks_per": marks})
    return out


async def _paper_data_from_request(req: dict) -> dict:
    book_id = req.get("book_id")
    if not book_id:
        raise HTTPException(status_code=400, detail="book_id is required")

    class_name = (req.get("class_name") or "").strip() or "Class 8"
    subject = (req.get("subject") or "").strip() or "General"
    school_name = (req.get("school_name") or "").strip() or "Examination"
    duration = (req.get("duration") or "").strip() or "1 Hour"
    chapter_ids = req.get("chapter_ids") or []

    async with async_session() as db:
        user = await _get_public_user(db)
        book = await db.get(Book, book_id)
        if not book or book.user_id != user.id:
            raise HTTPException(status_code=404, detail="Book not found")
        if book.status != "ready":
            raise HTTPException(status_code=400, detail="Book is still processing")

        # "All chapters" -> use every chapter for full-book coverage
        if not chapter_ids:
            chapter_ids = [c.id for c in (await db.execute(
                select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.order)
            )).scalars().all()]

        # Custom question mix if the user built one, else the class-based suggestion.
        custom = _clean_question_types(req.get("question_types") or [])
        if custom:
            question_types = custom
            difficulty = (req.get("difficulty") or "").strip() or _difficulty_and_structure(class_name)[0]
        else:
            difficulty, question_types = _difficulty_and_structure(class_name)

        return await generate_test_paper_questions(
            db=db, book_id=book_id, chapter_ids=chapter_ids,
            school_name=school_name, class_name=class_name, subject=subject,
            duration=duration, question_types=question_types,
            topic=req.get("topic") or subject, user_id=book.user_id,
            difficulty=difficulty,
        )


def _pdf_response(data: dict) -> Response:
    pdf_bytes = build_test_paper_pdf(data)
    subject = (data.get("subject") or "paper").replace(" ", "_").replace("/", "-")
    class_name = (data.get("class_name") or "").replace(" ", "_")
    filename = f"Test_Paper_{subject}_{class_name}.pdf".replace("__", "_")
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/public/test-paper/questions")
async def public_test_paper_questions(req: dict = Body(...)):
    """Generate the paper as structured JSON (editable in the UI)."""
    return await _paper_data_from_request(req)


@router.post("/public/test-paper/pdf")
async def public_test_paper_pdf(req: dict = Body(...)):
    """Build a PDF from (possibly edited) paper data."""
    if not req.get("questions"):
        raise HTTPException(status_code=400, detail="No questions to render")
    return _pdf_response(req)


@router.post("/public/test-paper")
async def public_test_paper(req: dict = Body(...)):
    data = await _paper_data_from_request(req)
    return _pdf_response(data)
