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
    re.compile(r"(?:Chapter|CHAPTER|Lesson|UNIT|Unit)\s+(\d+|[IVXLC]+)[\s:.\-–—]*(.*)", re.IGNORECASE),
    re.compile(r"^(\d+)\.\s+([A-Z][\w\s,;:'\"()\-–—&]+)$"),
    re.compile(r"^(Chapter|CHAPTER)\s+(\d+|[IVXLC]+)$", re.IGNORECASE),
    re.compile(r"^(Section|Part)\s+(\d+|[IVXLC]+)[\s:.\-–—]*(.*)", re.IGNORECASE),
]


def _get_text_fitz(file_path: str, page_num: int) -> str:
    doc = fitz.open(file_path)
    try:
        if page_num >= doc.page_count:
            return ""
        return doc[page_num].get_text()
    finally:
        doc.close()


def _get_text_pypdf(file_path: str, page_num: int) -> str:
    reader = PdfReader(file_path)
    try:
        if page_num >= len(reader.pages):
            return ""
        return reader.pages[page_num].extract_text() or ""
    finally:
        pass


def detect_chapters_from_pdf(file_path: str) -> list[dict]:
    chapters = []
    seen = set()

    if HAS_FITZ:
        doc = fitz.open(file_path)
        total_pages = doc.page_count
        for pi in range(total_pages):
            text = doc[pi].get_text()
            if not text:
                continue
            for line in text.split("\n"):
                line = line.strip()
                if len(line) < 3 or len(line) > 200:
                    continue
                for pattern in CHAPTER_PATTERNS:
                    match = pattern.match(line)
                    if match and line not in seen:
                        seen.add(line)
                        chapters.append({"title": line, "page_number": pi + 1})
                        break
        doc.close()
    else:
        reader = PdfReader(file_path)
        for pi, page in enumerate(reader.pages):
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                line = line.strip()
                if len(line) < 3 or len(line) > 200:
                    continue
                for pattern in CHAPTER_PATTERNS:
                    match = pattern.match(line)
                    if match and line not in seen:
                        seen.add(line)
                        chapters.append({"title": line, "page_number": pi + 1})
                        break

    if not chapters:
        return [{"title": "Full Book", "page_number": 1}]

    merged = [chapters[0]]
    for ch in chapters[1:]:
        if ch["page_number"] - merged[-1]["page_number"] >= 1:
            merged.append(ch)
        elif len(ch["title"]) > len(merged[-1]["title"]):
            merged[-1] = ch

    if len(merged) <= 1:
        return [{"title": "Full Book", "page_number": 1}]

    return merged


def extract_text_by_chapters(file_path: str, chapters: list[dict]) -> list[dict]:
    if HAS_FITZ:
        doc = fitz.open(file_path)
        total_pages = doc.page_count
        for i, chapter in enumerate(chapters):
            start_page = chapter["page_number"] - 1
            if i + 1 < len(chapters):
                next_page = chapters[i + 1]["page_number"] - 1
                end_page = max(start_page, next_page)
            else:
                end_page = total_pages
            chapter["start_page"] = start_page + 1
            chapter["end_page"] = max(start_page + 1, end_page)
            text_parts = []
            for pi in range(start_page, min(end_page, total_pages)):
                try:
                    pt = doc[pi].get_text()
                    if pt:
                        text_parts.append(pt)
                except Exception:
                    pass
            chapter["text"] = "\n\n".join(text_parts) if text_parts else chapter.get("title", "")
        doc.close()
    else:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        for i, chapter in enumerate(chapters):
            start_page = chapter["page_number"] - 1
            if i + 1 < len(chapters):
                next_page = chapters[i + 1]["page_number"] - 1
                end_page = max(start_page, next_page)
            else:
                end_page = total_pages
            chapter["start_page"] = start_page + 1
            chapter["end_page"] = max(start_page + 1, end_page)
            text_parts = []
            for pi in range(start_page, min(end_page, total_pages)):
                try:
                    pt = reader.pages[pi].extract_text()
                    if pt:
                        text_parts.append(pt)
                except Exception:
                    pass
            chapter["text"] = "\n\n".join(text_parts) if text_parts else chapter.get("title", "")

    return chapters


def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> list[dict]:
    cs = chunk_size or settings.chunk_size
    ov = overlap or settings.chunk_overlap

    sentences = text.replace("\n", " ").split(". ")
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        tentative = current_chunk + (". " if current_chunk else "") + sentence
        if len(tentative.split()) > cs and current_chunk:
            chunks.append({"text": current_chunk.strip(), "index": len(chunks)})
            words = current_chunk.split()
            overlap_words = words[-ov:] if len(words) > ov else words
            current_chunk = " ".join(overlap_words) + " " + sentence
        else:
            current_chunk = tentative

    if current_chunk.strip():
        chunks.append({"text": current_chunk.strip(), "index": len(chunks)})

    return chunks


async def process_book(
    file_path: str,
    book_title: str,
    on_progress=None,
) -> dict:
    logger.info(f"Processing book: {book_title}")

    chapters = detect_chapters_from_pdf(file_path)
    chapters = extract_text_by_chapters(file_path, chapters)

    if HAS_FITZ:
        doc = fitz.open(file_path)
        total_pages = doc.page_count
        doc.close()
    else:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        del reader

    all_chunks = []
    chunk_index = 0

    for chapter in chapters:
        if not chapter.get("text"):
            continue
        chapter_chunks = chunk_text(chapter["text"])
        for c in chapter_chunks:
            c["index"] = chunk_index
            c["chapter"] = {
                "title": chapter["title"],
                "start_page": chapter["start_page"],
                "end_page": chapter["end_page"],
            }
            chunk_index += 1
        all_chunks.extend(chapter_chunks)

    if on_progress:
        await on_progress(10)

    chunk_texts = [c["text"] for c in all_chunks]
    batch_size = 20
    all_embeddings = []

    for i in range(0, len(chunk_texts), batch_size):
        batch = chunk_texts[i : i + batch_size]
        embeddings = await create_embeddings_batch(batch)
        all_embeddings.extend(embeddings)
        if on_progress:
            progress = min(100, 10 + int((i + len(batch)) / len(chunk_texts) * 90))
            await on_progress(progress)

    for chunk, embedding in zip(all_chunks, all_embeddings):
        chunk["embedding"] = embedding
        chunk["embedding_json"] = json.dumps(embedding)

    return {
        "total_pages": total_pages,
        "total_chunks": len(all_chunks),
        "chunks": all_chunks,
        "chapters": [{"title": ch["title"], "start_page": ch["start_page"], "end_page": ch["end_page"]} for ch in chapters],
    }


def save_uploaded_file(file_content: bytes, filename: str) -> str:
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4()}_{filename}"
    file_path = os.path.join(settings.upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(file_content)
    return file_path
