import json
import os
import re
import uuid
import logging
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
from pypdf import PdfReader
import pypdf.filters
pypdf.filters._MAX_BYTES_DECOMPRESSED = 500_000_000
pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH = 500_000_000
from app.core.config import settings
from app.services.embedding_service import create_embeddings_batch

logger = logging.getLogger(__name__)


CHAPTER_PATTERNS = [
    re.compile(r"^(CHAPTER|Chapter)\s+([0-9]{1,2}|[IVXLC]{1,5})\b", re.IGNORECASE),
    re.compile(r"^(UNIT|Unit)\s+([0-9]{1,2}|[IVXLC]{1,5})\b", re.IGNORECASE),
    re.compile(r"^(Lesson|Section|Part|Topic)\s+([0-9]{1,2}|[IVXLC]{1,5})\b", re.IGNORECASE),
]


def clean_text(text: str) -> str:
    """Remove replacement chars, control chars, and collapse whitespace."""
    if not text:
        return ""
    text = text.replace("\ufffd", " ").replace("\u00a0", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pages(file_path: str) -> list[dict]:
    """Return [{page: n, text: ...}] in reading order (1-indexed)."""
    pages = []
    if HAS_FITZ:
        doc = fitz.open(file_path)
        for i in range(doc.page_count):
            pages.append({"page": i + 1, "text": clean_text(doc[i].get_text())})
        doc.close()
    else:
        reader = PdfReader(file_path)
        for i, page in enumerate(reader.pages):
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            pages.append({"page": i + 1, "text": clean_text(t)})
    return pages


HEADING_RE = re.compile(
    r"^(CHAPTER|Chapter|UNIT|Unit|LESSON|Lesson|SECTION|Section|PART|Part|TOPIC|Topic)"
    r"\s+([0-9]{1,2}|[IVXLC]{1,5})\b\s*:?\s*(.*)$"
)


def detect_chapters(pages: list[dict], file_path: str = None) -> list[dict]:
    """Best-effort chapter detection from the extracted page text (fast).

    Skips table-of-contents pages (which mention many chapters) and picks
    standalone headings like "CHAPTER 12 / ECOSYSTEM". Only used for
    navigation labels — chunk boundaries always follow page order.
    """
    found = []

    for p in pages:
        lines = [ln.strip() for ln in p["text"].split("\n") if ln.strip()]
        mentions = [ln for ln in lines if HEADING_RE.match(ln)]
        # A page naming 3+ chapters is a table of contents — not real starts.
        if len(mentions) >= 3:
            continue

        for i, line in enumerate(lines):
            if len(line) > 90:
                continue
            m = HEADING_RE.match(line)
            if not m:
                continue

            keyword, num, tail = m.group(1), m.group(2), m.group(3).strip()
            title = f"{keyword} {num}"
            # prefer a title on the same line, else the next ALL-CAPS line
            if tail and 3 <= len(tail) <= 70:
                title = f"{keyword} {num}: {tail[:70]}"
            elif i + 1 < len(lines):
                nxt = lines[i + 1]
                if nxt.isupper() and 3 <= len(nxt) <= 70:
                    title = f"{keyword} {num}: {nxt.title()}"
            found.append({"title": title, "page_number": p["page"]})
            break

    if len(found) <= 1:
        return [{"title": "Full Book", "page_number": 1}]

    # one per page, in page order
    per_page = []
    for ch in found:
        if not per_page or ch["page_number"] != per_page[-1]["page_number"]:
            per_page.append(ch)

    # drop bare duplicates ("Chapter 9" vs "CHAPTER 9: Biotechnology")
    seen = {}
    deduped = []
    for ch in per_page:
        m = HEADING_RE.match(ch["title"])
        key = f"{m.group(1).lower()} {m.group(2)}" if m else ch["title"].lower()
        if key in seen:
            idx = seen[key]
            if len(ch["title"]) > len(deduped[idx]["title"]):
                deduped[idx] = ch
        else:
            seen[key] = len(deduped)
            deduped.append(ch)
    return deduped


def chunk_pages(pages: list[dict], chunk_words: int = None, overlap_words: int = None) -> list[dict]:
    """Chunk the document in page order, tracking accurate page ranges."""
    cw = chunk_words or settings.chunk_size
    ow = overlap_words or settings.chunk_overlap

    chunks = []
    buf = ""
    start_page = None

    for p in pages:
        text = p["text"]
        if not text:
            continue
        if start_page is None:
            start_page = p["page"]
        buf = (buf + "\n" + text).strip()
        end_page = p["page"]

        words = buf.split()
        if len(words) >= cw:
            chunks.append({"text": buf, "page_start": start_page, "page_end": end_page})
            tail = words[-ow:] if len(words) > ow else words
            buf = " ".join(tail)
            start_page = p["page"]

    if buf.strip() and len(buf.split()) > 30:
        chunks.append({"text": buf.strip(), "page_start": start_page or 1, "page_end": pages[-1]["page"] if pages else 1})

    return chunks


def assign_chapter(chunk_page: int, chapters: list[dict]) -> dict:
    """Return the latest chapter starting at or before the chunk's page."""
    chosen = chapters[0] if chapters else {"title": "Full Book", "page_number": 1}
    for ch in chapters:
        if ch["page_number"] <= chunk_page:
            chosen = ch
        else:
            break
    return chosen


async def process_book(
    file_path: str,
    book_title: str,
    on_progress=None,
    user_id: str = None,
) -> dict:
    logger.info(f"Processing book: {book_title}")

    pages = extract_pages(file_path)
    total_pages = len(pages)

    chapters = detect_chapters(pages, file_path)

    # chunk strictly in page order
    raw_chunks = chunk_pages(pages)

    all_chunks = []
    for idx, c in enumerate(raw_chunks):
        ch = assign_chapter(c["page_start"], chapters)
        all_chunks.append({
            "index": idx,
            "text": c["text"],
            "page_start": c["page_start"],
            "page_end": c["page_end"],
            "chapter": {"title": ch["title"], "start_page": ch.get("page_number", 1)},
        })

    if on_progress:
        await on_progress(10)

    chunk_texts = [c["text"] for c in all_chunks]
    batch_size = 10
    batches = [chunk_texts[i : i + batch_size] for i in range(0, len(chunk_texts), batch_size)]

    # Embed batches IN PARALLEL (bounded) — embeddings are network-bound, so
    # running several at once cuts total time dramatically.
    import asyncio as _asyncio
    sem = _asyncio.Semaphore(6)
    done = {"n": 0}

    async def _embed(batch):
        async with sem:
            res = await create_embeddings_batch(batch, user_id)
            done["n"] += len(batch)
            if on_progress:
                pct = min(100, 10 + int(done["n"] / max(len(chunk_texts), 1) * 90))
                try:
                    await on_progress(pct)
                except Exception:
                    pass
            return res

    results = await _asyncio.gather(*[_embed(b) for b in batches], return_exceptions=True)
    all_embeddings = []
    for r in results:
        if isinstance(r, Exception):
            raise r
        all_embeddings.extend(r)

    for chunk, embedding in zip(all_chunks, all_embeddings):
        chunk["embedding"] = embedding
        chunk["embedding_json"] = json.dumps(embedding)

    return {
        "total_pages": total_pages,
        "total_chunks": len(all_chunks),
        "chunks": all_chunks,
        "chapters": [
            {"title": ch["title"], "start_page": ch["page_number"], "end_page": ch["page_number"]}
            for ch in chapters
        ],
    }


def save_uploaded_file(file_content: bytes, filename: str) -> str:
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4()}_{filename}"
    file_path = os.path.join(settings.upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(file_content)
    return file_path
