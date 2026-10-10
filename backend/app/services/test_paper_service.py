import json
import io
import re
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fpdf import FPDF
from app.models import Book, Chapter, BookChunk
from app.services.llm_gateway import llm_gateway, Provider
from app.services.rag_service import retrieve_relevant_chunks
from app.core.config import settings

logger = logging.getLogger(__name__)


def sanitize_text(text: str) -> str:
    if not text:
        return ""
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "--", "\u2026": "...",
        "\u00a0": " ", "\u00ad": "-",
        "\u2192": "->", "\u2190": "<-", "\u2191": "^", "\u2193": "v",
        "\u2264": "<=", "\u2265": ">=", "\u00d7": "x", "\u00f7": "/",
        "\u03b1": "alpha", "\u03b2": "beta", "\u03b3": "gamma",
        "\u03b4": "delta", "\u03b8": "theta", "\u03c0": "pi",
        "\u03a9": "Omega", "\u03a3": "Sigma",
        "\u00b0": " deg ", "\u00b2": "^2", "\u00b3": "^3",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = re.sub(r'[^\x00-\x7F\u00A0-\u00FF]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def wrap_text(text: str, max_chars: int = 95) -> str:
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = (current + " " + word).strip()
        else:
            if current:
                lines.append(current)
            if len(word) > max_chars:
                for j in range(0, len(word), max_chars):
                    lines.append(word[j:j + max_chars])
                current = ""
            else:
                current = word
    if current:
        lines.append(current)
    return "\n".join(lines)


TEST_PAPER_PROMPT = """You are a professional exam paper creator. Generate a test paper based on the content below.

SCHOOL: {school_name}
CLASS: {class_name}
SUBJECT: {subject}
DURATION: {duration}
TOPIC: {topic}
DIFFICULTY: {difficulty}

BOOK CONTENT:
{context}

QUESTION STRUCTURE (generate EXACTLY these numbers of questions):
{question_structure}

RULES:
1. Generate EXACTLY the specified number of questions for each type.
2. Questions MUST be based on the provided book content only.
3. Match the difficulty to the CLASS standard described above — do not make it
   harder or easier than that class level.
4. Return ONLY valid JSON — no markdown, no explanations.
5. Use the exact "type" value given for each question. Supported types:
   - "mcq": 4 options {{A,B,C,D}}; "answer" = the correct letter.
   - "assertion_reason": 4 options {{A,B,C,D}}; "answer" = the correct letter.
   - "true_false": "answer" = "True" or "False".
   - "fill_blank": write the question with a blank "__________"; "answer" = the missing word.
   - "match": put the two columns in the question text as "Column A: ... | Column B: ...".
   - "very_short", "short_answer", "long_answer", "case_study": just "question" (+ optional "answer").
6. Number questions sequentially across all types (1, 2, 3...).

JSON FORMAT:
{{
  "questions": [
    {{
      "number": 1,
      "type": "mcq",
      "question": "What is...?",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "answer": "B",
      "marks": 1
    }},
    {{
      "number": 5,
      "type": "short_answer",
      "question": "Explain the process of...",
      "marks": 2
    }}
  ]
}}

Generate now:"""


def _build_structure_text(question_types: list[dict]) -> str:
    lines = []
    for qt in question_types:
        lines.append(f"- {qt['label']}: {qt['count']} questions, {qt['marks_per']} marks each = {qt['count'] * qt['marks_per']} marks total")
    return "\n".join(lines)


def _build_structure_prompt(question_types: list[dict]) -> str:
    lines = []
    for qt in question_types:
        lines.append(f"- {qt['label']}: exactly {qt['count']} questions")
    return "\n".join(lines)


async def generate_test_paper_questions(
    db: AsyncSession,
    book_id: str,
    chapter_ids: list[str],
    school_name: str,
    class_name: str,
    subject: str,
    duration: str,
    question_types: list[dict],
    topic: str = "",
    user_id: str = None,
    difficulty: str = "",
) -> dict:
    book = await db.get(Book, book_id)
    if not book:
        raise ValueError("Book not found")

    # Pull chunks straight from the selected chapters — deterministic and fast
    # (no embedding/rerank round-trips, which otherwise risk serverless timeouts).
    if chapter_ids:
        result = await db.execute(
            select(BookChunk)
            .where(BookChunk.book_id == book_id, BookChunk.chapter_id.in_(chapter_ids))
            .order_by(BookChunk.chunk_index)
        )
        rows = list(result.scalars().all())
    else:
        rows = []

    if not rows:
        result = await db.execute(
            select(BookChunk).where(BookChunk.book_id == book_id)
            .order_by(BookChunk.chunk_index).limit(15)
        )
        rows = list(result.scalars().all())

    # evenly sample up to 12 chunks so the whole selected range is represented
    if len(rows) > 12:
        step = len(rows) / 12
        rows = [rows[int(i * step)] for i in range(12)]

    all_chunks = [
        {"id": c.id, "content": c.content, "chunk_index": c.chunk_index,
         "page_start": c.page_start, "page_end": c.page_end}
        for c in rows
    ]

    context = "\n\n---\n\n".join(c["content"][:1500] for c in all_chunks[:12])

    prompt = TEST_PAPER_PROMPT.format(
        school_name=school_name,
        class_name=class_name,
        subject=subject,
        duration=duration,
        topic=topic or subject,
        context=context,
        question_structure=_build_structure_prompt(question_types),
        difficulty=difficulty or "appropriate for the class level",
    )

    response = await llm_gateway.chat(
        messages=[
            {"role": "system", "content": "You are an exam paper generator. Output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=8192,
        user_id=user_id,
    )

    if user_id:
        try:
            from app.services import usage_service
            await usage_service.log_usage(
                db, user_id, response.provider, response.model, "/test-paper",
                tokens_in=response.tokens_in, tokens_out=response.tokens_out,
                response_time_ms=response.response_time_ms, book_id=book_id,
            )
        except Exception:
            pass

    try:
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {
            "questions": [],
            "raw": response.content,
        }

    return {
        "questions": data.get("questions", []),
        "school_name": school_name,
        "class_name": class_name,
        "subject": subject,
        "duration": duration,
        "topic": topic,
        "question_types": question_types,
        "total_marks": sum(qt["count"] * qt["marks_per"] for qt in question_types),
    }


def build_test_paper_pdf(data: dict) -> bytes:
    """Render a clean question paper (no answer-writing space — answers go on a
    separate answer sheet)."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    def s(text):
        if isinstance(text, (bytes, bytearray)):
            text = text.decode("utf-8", errors="replace")
        return sanitize_text(str(text))

    school = s(data.get("school_name") or "Examination")
    class_name = s(data.get("class_name") or "")
    subject = s(data.get("subject") or "")
    duration = s(data.get("duration") or "")
    total_marks = data.get("total_marks", 0)
    questions = data.get("questions", [])

    left, right = 15, 195
    content_w = right - left  # 180

    # ── Header box ──
    pdf.set_line_width(0.6)
    pdf.rect(left, 12, content_w, 26)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_xy(left, 15)
    pdf.cell(content_w, 7, school, align="C")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(left, 22.5)
    pdf.cell(content_w, 6, "  |  ".join(x for x in [class_name, subject] if x), align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(left, 30)
    pdf.cell(content_w, 5, f"Time: {duration}          Maximum Marks: {total_marks}", align="C")

    pdf.set_y(44)
    pdf.set_line_width(0.3)
    pdf.line(left, pdf.get_y(), right, pdf.get_y())
    pdf.ln(3)

    # ── General instructions ──
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_x(left)
    pdf.cell(0, 5, "General Instructions:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    for inst in [
        "1. All questions are compulsory.",
        "2. Read each question carefully before answering.",
        "3. Write your answers neatly on the answer sheet provided.",
        f"4. This paper carries a maximum of {total_marks} marks.",
    ]:
        pdf.set_x(left)
        pdf.multi_cell(content_w, 5, inst)

    pdf.ln(2)
    pdf.set_line_width(0.3)
    pdf.line(left, pdf.get_y(), right, pdf.get_y())
    pdf.ln(5)

    # ── Questions ──
    num_w = 9
    for i, q in enumerate(questions):
        q_num = q.get("number", i + 1)
        q_type = q.get("type", "")
        marks = q.get("marks", 1)
        question_text = s(q.get("question", "")) or "(question)"

        if pdf.get_y() > 250:
            pdf.add_page()

        y0 = pdf.get_y()
        # hanging indent: number, then wrapped question text aligned after it
        pdf.set_x(left)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(num_w, 5.5, f"{q_num}.")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_x(left + num_w)
        pdf.multi_cell(content_w - num_w - 15, 5.5, question_text)
        y_after = pdf.get_y()

        # marks right-aligned on the first line
        pdf.set_xy(right - 14, y0)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(14, 5.5, f"[{marks}]", align="R")
        pdf.set_y(y_after)

        # options for MCQ / assertion-reason
        if q_type in ("mcq", "assertion_reason") and q.get("options"):
            pdf.set_font("Helvetica", "", 10)
            for opt_key in ["A", "B", "C", "D"]:
                opt_text = s(q["options"].get(opt_key, ""))
                if not opt_text:
                    continue
                pdf.set_x(left + num_w)
                pdf.multi_cell(content_w - num_w - 15, 5.5, f"({opt_key}) {opt_text}")

        pdf.ln(3)

    # ── Footer ──
    pdf.set_line_width(0.3)
    pdf.line(left, pdf.get_y() + 2, right, pdf.get_y() + 2)
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 6, "--- End of Question Paper ---", align="C")

    result = pdf.output()
    return bytes(result) if isinstance(result, bytearray) else result
