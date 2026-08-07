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
import pypdf.filters
pypdf.filters._MAX_BYTES_DECOMPRESSED = 500_000_000
pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH = 500_000_000

async def main():
    filepath = "12th class biology.pdf"
    email = "fix@test.com"
    title = "12th Class Biology"
    author = "NCERT"

    async with async_session() as db:
        r = await db.execute(select(User).where(User.email == email))
        user = r.scalar_one_or_none()
        if not user:
            print("User not found")
            return

        filesize = os.path.getsize(filepath)
        print(f"[1/5] Copying PDF ({filesize/1024/1024:.0f}MB)...")
        with open(filepath, "rb") as f:
            local_path = save_uploaded_file(f.read(), os.path.basename(filepath))

        book = Book(id=str(uuid.uuid4()), user_id=user.id, title=title, author=author,
                     file_path=local_path, file_size=filesize, status="processing")
        db.add(book)
        await db.flush()
        await db.commit()

        t_total = time.time()
        t0 = time.time()
        print(f"[2/5] Detecting chapters...")
        chapters = detect_chapters_from_pdf(local_path)
        print(f"    Found {len(chapters)} chapters ({time.time()-t0:.0f}s)")

        t0 = time.time()
        print(f"[3/5] Extracting text by chapter...")
        chapters = extract_text_by_chapters(local_path, chapters)
        print(f"    Done ({time.time()-t0:.0f}s)")

        t0 = time.time()
        print(f"[4/5] Chunking + embedding (this takes longest)...")
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
        print(f"    {len(all_chunks)} chunks from {len(chapters)} chapters")

        total = len(all_chunks)
        texts = [c["text"] for c in all_chunks]
        batch_size = 20
        embeddings = []
        for i in range(0, total, batch_size):
            batch = texts[i:i+batch_size]
            emb = await create_embeddings_batch(batch)
            embeddings.extend(emb)
            pct = min(100, int((i + len(batch)) / total * 100))
            elapsed = time.time() - t_total
            print(f"    Embeddings: {pct}% ({i+len(batch)}/{total}) - {elapsed:.0f}s elapsed")

        for chunk, emb in zip(all_chunks, embeddings):
            chunk["embedding_json"] = json.dumps(emb)

        print(f"    All embeddings done ({time.time()-t0:.0f}s)")

        t0 = time.time()
        print(f"[5/5] Saving to database...")
        chapter_map = {}
        for i, ch in enumerate(chapters, 1):
            c = Chapter(id=str(uuid.uuid4()), book_id=book.id, title=ch["title"],
                         order=i, start_page=ch["start_page"], end_page=ch["end_page"])
            db.add(c)
            await db.flush()
            chapter_map[ch["title"]] = c.id

        for chunk in all_chunks:
            ch_title = chunk.get("chapter", {}).get("title", "")
            bk = BookChunk(id=str(uuid.uuid4()), book_id=book.id,
                           chapter_id=chapter_map.get(ch_title),
                           chunk_index=chunk["index"], content=chunk["text"],
                           embedding_json=chunk.get("embedding_json"))
            db.add(bk)

        book.status = "ready"
        book.total_chunks = len(all_chunks)
        book.total_pages = len(set(ch["start_page"] for ch in chapters))
        await db.commit()

        elapsed = time.time() - t_total
        print(f"    Saved ({time.time()-t0:.0f}s)")
        print(f"\nDONE in {elapsed:.0f}s!")
        print(f"  {len(chapters)} chapters, {len(all_chunks)} chunks")
        print(f"  Login: fix@test.com / test1234")
        print(f"  Visit: https://frontend-ten-orcin-456yf3zvl2.vercel.app")

asyncio.run(main())
