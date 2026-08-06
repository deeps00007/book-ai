import json
import os
import re
import uuid
import logging
import fitz
from app.core.config import settings
from app.services.embedding_service import create_embeddings_batch

logger = logging.getLogger(__name__)


CHAPTER_PATTERNS = [
    re.compile(r"(?:Chapter|CHAPTER|Lesson|UNIT|Unit)\s+(\d+|[IVXLC]+)[\s:.\-–—]*(.*)", re.IGNORECASE),
    re.compile(r"^(\d+)\.\s+([A-Z][\w\s,;:'\"()\-–—&]+)$"),
    re.compile(r"^(Chapter|CHAPTER)\s+(\d+|[IVXLC]+)$", re.IGNORECASE),
    re.compile(r"^(Section|Part)\s+(\d+|[IVXLC]+)[\s:.\-–—]*(.*)", re.IGNORECASE),
]


def detect_chapters_from_pdf(file_path: str) -> list[dict]:
    doc = fitz.open(file_path)
    chapters = []
    font_samples = []

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    font_samples.append(span["size"])

    median_size = 10.0
    if font_samples:
        font_samples.sort()
        median_size = font_samples[len(font_samples) // 2]

    for pi, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]
        page_headings = []
        page_text = page.get_text()

        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                line_text = "".join(s["text"] for s in line["spans"]).strip()
                if not line_text or len(line_text) < 3 or len(line_text) > 200:
                    continue

                max_font_size = max((s["size"] for s in line["spans"]), default=0)
                is_bold = any(s["flags"] & 2 for s in line["spans"])

                is_heading = (max_font_size >= median_size * 1.15) or is_bold or (
                    max_font_size >= median_size and
                    len(line_text) < 80 and
                    (line_text[0].isdigit() or line_text.isupper() or line_text[0].isupper())
                )

                if not is_heading:
                    continue

                for pattern in CHAPTER_PATTERNS:
                    match = pattern.match(line_text)
                    if match:
                        page_headings.append({
                            "title": line_text,
                            "page_number": pi + 1,
                            "font_size": max_font_size,
                        })
                        break

        if page_headings:
            best = max(page_headings, key=lambda h: h["font_size"])
            chapters.append(best)

    merged = []
    for ch in chapters:
        if not merged or ch["page_number"] - merged[-1]["page_number"] >= 2:
            merged.append(ch)
        elif ch["font_size"] >= merged[-1]["font_size"]:
            merged[-1] = ch

    if len(merged) <= 1:
        for pi, page in enumerate(doc):
            text = page.get_text()
            for line in text.split("\n"):
                line = line.strip()
                if len(line) < 3 or len(line) > 200:
                    continue
                for pattern in CHAPTER_PATTERNS:
                    match = pattern.match(line)
                    if match:
                        merged.append({
                            "title": line,
                            "page_number": pi + 1,
                            "font_size": median_size,
                        })
                        break

    if len(merged) <= 1:
        merged = [
            {"title": "Full Book", "page_number": 1, "font_size": median_size}
        ]

    doc.close()
    return merged


def extract_text_by_chapters(file_path: str, chapters: list[dict]) -> list[dict]:
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
        real_end = min(end_page, total_pages)
        for pi in range(start_page, max(start_page + 1, real_end)):
            text_parts.append(doc[pi].get_text())
        chapter["text"] = "\n\n".join(text_parts) if text_parts else chapter.get("title", "")

    doc.close()
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

    doc = fitz.open(file_path)
    total_pages = doc.page_count
    doc.close()

    chapters = detect_chapters_from_pdf(file_path)
    chapters = extract_text_by_chapters(file_path, chapters)

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
