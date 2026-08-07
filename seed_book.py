"""Usage: python seed_book.py "mybook.pdf" "Book Title" "Author"

Processes a large PDF locally with PyMuPDF (50x faster than pypdf)
and writes results to Supabase for use on the live app.
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

import asyncio, json, uuid

os.environ["USE_SQLITE"] = "false"
os.environ["DATABASE_URL"] = "postgresql://postgres.ynltzrdihjycufniyvlk:SupabaseDBPassword1!@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
os.environ["FIREWORKS_API_KEY"] = "fw_URSNoRJPREb9orbdGzC23N"
os.environ["FIREWORKS_BASE_URL"] = "https://api.fireworks.ai/inference/v1"

from app.core.database import async_session
from app.models import User, Book, Chapter, BookChunk
from app.services.upload_service import save_uploaded_file, detect_chapters_from_pdf, extract_text_by_chapters, chunk_text
from app.services.embedding_service import create_embeddings_batch
from sqlalchemy import select

async def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else "12th class biology.pdf"
    title = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(filepath))[0]
    author = sys.argv[3] if len(sys.argv) > 3 else ""
    email = sys.argv[4] if len(sys.argv) > 4 else "fix@test.com"

    async with async_session() as db:
        r = await db.execute(select(User).where(User.email == email))
        user = r.scalar_one_or_none()
        if not user:
            print(f"User {email} not found")
            return

        filesize = os.path.getsize(filepath)
        print(f"File: {filesize/1024/1024:.1f}MB -> '{title}'")

        with open(filepath, "rb") as f:
            local_path = save_uploaded_file(f.read(), os.path.basename(filepath))

        book = Book(id=str(uuid.uuid4()), user_id=user.id, title=title, author=author,
                     file_path=local_path, file_size=filesize, status="processing")
        db.add(book)
        await db.flush()
        await db.commit()

        t0 = time.time()
        chapters = detect_chapters_from_pdf(local_path)
        print(f"  Chapters: {len(chapters)} ({time.time()-t0:.0f}s)")

        t0 = time.time()
        chapters = extract_text_by_chapters(local_path, chapters)
        print(f"  Text extracted ({time.time()-t0:.0f}s)")

        all_chunks = []
        idx = 0
        for ch in chapters:
            if not ch.get("text"):
                continue
            for c in chunk_text(ch["text"]):
                c["index"] = idx
                c["chapter"] = {"title": ch["title"], "start_page": ch["start_page"], "end_page": ch["end_page"]}
                idx += 1
                all_chunks.append(c)
        total = len(all_chunks)
        print(f"  Chunks: {total}")

        t0 = time.time()
        texts = [c["text"] for c in all_chunks]
        batch_size = 20
        embeddings = []
        for i in range(0, total, batch_size):
            batch = texts[i:i+batch_size]
            emb = await create_embeddings_batch(batch)
            embeddings.extend(emb)
            pct = min(100, int((i + len(batch)) / total * 100))
            print(f"  Embeddings: {pct}% ({i+len(batch)}/{total})")

        for chunk, emb in zip(all_chunks, embeddings):
            chunk["embedding_json"] = json.dumps(emb)
        print(f"  Embeddings done ({time.time()-t0:.0f}s)")

        chapter_map = {}
        for i, ch in enumerate(chapters, 1):
            c = Chapter(id=str(uuid.uuid4()), book_id=book.id, title=ch["title"],
                         order=i, start_page=ch["start_page"], end_page=ch["end_page"])
            db.add(c)
            await db.flush()
            chapter_map[ch["title"]] = c.id

        for chunk in all_chunks:
            bk = BookChunk(id=str(uuid.uuid4()), book_id=book.id,
                           chapter_id=chapter_map.get(chunk.get("chapter", {}).get("title", "")),
                           chunk_index=chunk["index"], content=chunk["text"],
                           embedding_json=chunk.get("embedding_json"))
            db.add(bk)

        book.status = "ready"
        book.total_chunks = total
        book.total_pages = len(set(ch["start_page"] for ch in chapters))
        await db.commit()

        print(f"\nDONE! {len(chapters)} chapters, {total} chunks")
        print(f"Login: {email} / test1234")
        print(f"Visit: https://frontend-ten-orcin-456yf3zvl2.vercel.app")

asyncio.run(main())
