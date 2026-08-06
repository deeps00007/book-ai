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

BOOK CONTENT:
{context}

QUESTION STRUCTURE (generate EXACTLY these numbers of questions):
{question_structure}

RULES:
1. Generate EXACTLY the specified number of questions for each type.
2. Questions MUST be based on the provided book content.
3. Return ONLY valid JSON — no markdown, no explanations.
4. For MCQs, include 4 options (A,B,C,D) and mark the correct answer.
5. Number questions sequentially across all types (1, 2, 3...).

JSON FORMAT:
{{
  "questions": [
    {{
      "number": 1,
      "type": "mcq",
      "question": "What is...?",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "answer": "B",
      "marks": 2
    }},
    {{
      "number": 5,
      "type": "short_answer",
      "question": "Explain the process of...",
      "marks": 5
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
) -> dict:
    book = await db.get(Book, book_id)
    if not book:
        raise ValueError("Book not found")

    all_chunks = []
    for ch_id in chapter_ids:
        chunks = await retrieve_relevant_chunks(db, book_id, ", ".join(
            qt["label"] for qt in question_types
        ), top_k=6, chapter_id=ch_id)
        all_chunks.extend(chunks)

    if not all_chunks:
        result = await db.execute(
            select(BookChunk).where(BookChunk.book_id == book_id).limit(10)
        )
        all_chunks = [
            {"id": c.id, "content": c.content, "chunk_index": c.chunk_index, "page_start": c.page_start, "page_end": c.page_end, "similarity": 1.0}
            for c in result.scalars().all()
        ]

    context = "\n\n---\n\n".join(c["content"][:1500] for c in all_chunks[:10])

    prompt = TEST_PAPER_PROMPT.format(
        school_name=school_name,
        class_name=class_name,
        subject=subject,
        duration=duration,
        topic=topic or subject,
        context=context,
        question_structure=_build_structure_prompt(question_types),
    )

    response = await llm_gateway.chat(
        messages=[
            {"role": "system", "content": "You are an exam paper generator. Output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=8192,
    )

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
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    def s(text):
        if isinstance(text, (bytes, bytearray)):
            text = text.decode("utf-8", errors="replace")
        return sanitize_text(str(text))

    school = s(data["school_name"])
    class_name = s(data["class_name"])
    subject = s(data["subject"])
    duration = s(data["duration"])
    total_marks = data["total_marks"]
    questions = data["questions"]

    border_width = 0.8
    margin_x = 15
    content_w = 180

    pdf.set_line_width(border_width)
    pdf.rect(margin_x, 10, content_w, 27)

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_xy(0, 14)
    pdf.cell(210, 7, school, align="C")

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(0, 22)
    pdf.cell(210, 7, f"{class_name} | {subject}", align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(0, 30)
    pdf.cell(210, 5, f"Duration: {duration} | Maximum Marks: {total_marks}", align="C")

    pdf.ln(15)

    pdf.set_line_width(0.4)
    pdf.line(margin_x, pdf.get_y(), margin_x + content_w, pdf.get_y())
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, "GENERAL INSTRUCTIONS:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    instructions = [
        "1. This question paper contains questions of different types.",
        "2. All questions are compulsory.",
        "3. Read each question carefully before answering.",
        f"4. Maximum marks: {total_marks}",
    ]
    for inst in instructions:
        pdf.cell(0, 5, inst, ln=True)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, "QUESTION STRUCTURE:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    for qt in data["question_types"]:
        pdf.cell(0, 5, f"  {qt['label']}: {qt['count']} x {qt['marks_per']} = {qt['count'] * qt['marks_per']} marks", ln=True)

    pdf.ln(4)
    pdf.set_line_width(0.4)
    pdf.line(margin_x, pdf.get_y(), margin_x + content_w, pdf.get_y())
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "QUESTIONS", align="C", ln=True)
    pdf.ln(4)

    for i, q in enumerate(questions):
        if pdf.get_y() > 250:
            pdf.add_page()

        q_num = q.get("number", i + 1)
        q_type = q.get("type", "")
        marks = q.get("marks", 1)
        question_text = s(q.get("question", ""))
        question_text = wrap_text(question_text, max_chars=95)

        pdf.set_font("Helvetica", "B", 10)
        prefix = f"{q_num}. [{marks}]  "
        pdf.set_x(margin_x)
        pdf.cell(content_w, 6, prefix, ln=True)

        pdf.set_x(margin_x + 10)
        pdf.set_font("Helvetica", "", 10)
        for line in question_text.split("\n"):
            pdf.cell(content_w - 10, 6, line, ln=True)

        pdf.ln(1)

        if q_type == "mcq" and q.get("options"):
            pdf.set_font("Helvetica", "", 10)
            for opt_key in ["A", "B", "C", "D"]:
                opt_text = s(q["options"].get(opt_key, ""))
                if opt_text:
                    wrapped = wrap_text(f"({opt_key}) {opt_text}", max_chars=85)
                    for line in wrapped.split("\n"):
                        pdf.set_x(margin_x + 15)
                        pdf.cell(content_w - 15, 6, line, ln=True)

        if q_type in ("short_answer", "long_answer", "answer"):
            line_count = 3 if q_type == "short_answer" else 5
            for _ in range(line_count):
                pdf.set_draw_color(180, 180, 180)
                pdf.set_line_width(0.2)
                pdf.line(margin_x + 15, pdf.get_y() + 3, margin_x + content_w, pdf.get_y() + 3)
                pdf.ln(6)

        pdf.ln(3)

    pdf.set_line_width(0.4)
    pdf.line(margin_x, pdf.get_y() + 2, margin_x + content_w, pdf.get_y() + 2)
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 6, "--- End of Question Paper ---", align="C")

    result = pdf.output()
    return bytes(result) if isinstance(result, bytearray) else result
