"""
Background book-processing worker.

Polls the database for books with status "uploaded" (queued by the web app),
downloads them from Google Drive, extracts chapters + chunks + embeddings,
and marks them "ready".

Run it on any machine that stays on:

    python worker.py

This bypasses serverless time limits, so books of ANY size work.
"""

import sys
import os
import time
import asyncio
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))


def load_env():
    """Load secrets from backend/.env (falling back to root .env)."""
    for path in ("backend/.env", ".env"):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip("'").strip('"')
                os.environ[k.strip()] = v
        break


load_env()
os.environ["USE_SQLITE"] = "false"  # the worker always uses the shared database
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres.ynltzrdihjycufniyvlk:SupabaseDBPassword1!@aws-0-ap-south-1.pooler.supabase.com:6543/postgres",
)

from app.core.database import async_session
from app.models import Book, Chapter, BookChunk
from app.services.upload_service import process_book, save_uploaded_file, HAS_FITZ
from app.services import google_drive_service
from sqlalchemy import select, text

POLL_SECONDS = 8


async def process_one(book_id: str):
    async with async_session() as db:
        book = await db.get(Book, book_id)
        if not book or book.status not in ("uploaded", "processing"):
            return

        print(f"  -> downloading '{book.title}' from Drive...", flush=True)
        t0 = time.time()

        if not (book.file_path and book.file_path.startswith("drive:")):
            print("    (not a Drive book, skipping)", flush=True)
            return
        drive_id = book.file_path.split("drive:", 1)[1]

        try:
            content = await google_drive_service.download_file(drive_id)
        except Exception as e:
            book.status = "failed"
            book.error_message = f"Drive download failed: {str(e)[:200]}"
            await db.commit()
            print(f"    download failed: {e}", flush=True)
            return

        print(f"    {len(content)/1024/1024:.1f} MB in {time.time()-t0:.0f}s", flush=True)

        await db.execute(text("DELETE FROM book_chunks WHERE book_id = :b"), {"b": book.id})
        await db.execute(text("DELETE FROM chapters WHERE book_id = :b"), {"b": book.id})
        book.status = "processing"
        await db.commit()

        fp = save_uploaded_file(content, f"worker_{book.id[:8]}.pdf")

        try:
            t0 = time.time()
            result = await process_book(fp, book.title, user_id=book.user_id)
            print(f"    {result['total_pages']} pages, {result['total_chunks']} chunks in {time.time()-t0:.0f}s", flush=True)

            cmap = {}
            for order, ci in enumerate(result.get("chapters", []), 1):
                ch = Chapter(id=str(uuid.uuid4()), book_id=book.id, title=ci["title"],
                             order=order, start_page=ci["start_page"], end_page=ci["end_page"])
                db.add(ch)
                await db.flush()
                cmap[ci["title"]] = ch.id

            for ck in result["chunks"]:
                db.add(BookChunk(
                    id=str(uuid.uuid4()), book_id=book.id,
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
            print(f"    OK READY: {book.title}", flush=True)
        except Exception as e:
            book.status = "failed"
            book.error_message = str(e)[:300]
            await db.commit()
            print(f"    FAIL failed: {e}", flush=True)


async def process_all_pending(max_books: int = 20):
    """Process every queued book, then return."""
    processed = 0
    while processed < max_books:
        async with async_session() as db:
            result = await db.execute(
                select(Book)
                .where(Book.status.in_(["uploaded", "processing"]))
                .order_by(Book.created_at)
                .limit(1)
            )
            book = result.scalar_one_or_none()
        if not book:
            break
        print(f"\n[{time.strftime('%H:%M:%S')}] Processing: {book.title}", flush=True)
        await process_one(book.id)
        processed += 1
    print(f"Done. Processed {processed} book(s).", flush=True)


async def main():
    once = "--once" in sys.argv

    print("=" * 60, flush=True)
    print("Book AI worker started", flush=True)
    print(f"  PyMuPDF (fast): {HAS_FITZ}", flush=True)
    print(f"  Mode: {'once (process all then exit)' if once else 'continuous'}", flush=True)
    print("=" * 60, flush=True)

    if once:
        await process_all_pending()
        return

    print(f"  Polling every {POLL_SECONDS}s for queued books...", flush=True)
    print("  Press Ctrl+C to stop.", flush=True)

    while True:
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(Book)
                    .where(Book.status.in_(["uploaded", "processing"]))
                    .order_by(Book.created_at)
                    .limit(1)
                )
                book = result.scalar_one_or_none()
            if book:
                print(f"\n[{time.strftime('%H:%M:%S')}] Found queued book: {book.title}", flush=True)
                await process_one(book.id)
            else:
                await asyncio.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            print("Stopped.", flush=True)
            break
        except Exception as e:
            print(f"Worker error: {e}", flush=True)
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
