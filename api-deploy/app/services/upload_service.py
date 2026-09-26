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


def detect_chapters(pages: list[dict], file_path: str) -> list[dict]:
    """Best-effort chapter detection using large-font headings only.

    Never used for chunk boundaries (chunking follows page order), only for
    navigation labels. Falls back to a single 'Full Book' chapter.
    """
    found = []

    if HAS_FITZ:
        try:
            doc = fitz.open(file_path)
            sizes = []
            for page in doc:
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines", []):
                        for span in line["spans"]:
                            sizes.append(span["size"])
            sizes.sort()
            median = sizes[len(sizes) // 2] if sizes else 10.0
            threshold = median * 1.35

            current = None
            for i in range(doc.page_count):
                page = doc[i]
                best = None
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines", []):
                        line_text = "".join(s["text"] for s in line["spans"]).strip()
                        if not line_text or len(line_text) > 90:
                            continue
                        max_size = max((s["size"] for s in line["spans"]), default=0)
                        if max_size < threshold:
                            continue
                        for pat in CHAPTER_PATTERNS:
                            if pat.match(line_text):
                                if best is None or max_size > best[1]:
                                    best = (line_text, max_size)
                                break
                if best and (current is None or best[0] != current[0]):
                    found.append({"title": best[0], "page_number": i + 1})
                    current = best
            doc.close()
        except Exception as e:
            logger.warning(f"Chapter detection failed: {e}")

    if not found:
        return [{"title": "Full Book", "page_number": 1}]

    # dedupe consecutive / same page
    merged = []
    for ch in found:
        if not merged or ch["page_number"] != merged[-1]["page_number"]:
            merged.append(ch)
    return merged


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
    batch_size = 20
    all_embeddings = []

    for i in range(0, len(chunk_texts), batch_size):
        batch = chunk_texts[i : i + batch_size]
        embeddings = await create_embeddings_batch(batch, user_id)
        all_embeddings.extend(embeddings)
        if on_progress:
            progress = min(100, 10 + int((i + len(batch)) / max(len(chunk_texts), 1) * 90))
            await on_progress(progress)

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
