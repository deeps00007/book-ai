from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User, Book, GeneratedContent
from app.schemas import GenerateRequest, GenerateResponse
from app.services.llm_gateway import llm_gateway, Provider
from app.services.rag_service import retrieve_relevant_chunks, build_rag_prompt
import json

router = APIRouter()


PROMPTS = {
    "worksheet": """Create a detailed worksheet based on the book excerpts provided.
Include:
1. Title and grade level
2. 5-8 questions of varying difficulty
3. Include multiple choice, short answer, and long answer questions
4. Space for student name and date
Format as structured JSON with keys: title, grade_level, instructions, questions (array with type, question, marks, difficulty).""",

    "lesson_plan": """Create a detailed lesson plan from the book excerpts.
Include:
1. Lesson title and duration
2. Learning objectives
3. Materials needed
4. Step-by-step lesson flow
5. Assessment methods
Format as structured JSON with keys: title, duration, objectives, materials, lesson_flow, assessment.""",

    "test": """Create a comprehensive test paper based on the book excerpts.
Include:
1. Test title and total marks
2. Time duration
3. Sections with different question types
4. Marking scheme
Format as structured JSON with keys: title, total_marks, duration, sections (array with type, questions, marks).""",

    "notes": """Create detailed study notes from the book excerpts.
Include:
1. Key concepts
2. Definitions
3. Important formulas
4. Summary points
Format as structured JSON with keys: title, key_concepts, definitions, formulas, summary.""",

    "summary": """Create a concise summary of the book excerpts.
Include:
1. Main topic
2. Key points (5-7 bullet points)
3. Important takeaways
Format as structured JSON with keys: title, main_topic, key_points, takeaways.""",

    "flashcards": """Create flashcards from the book excerpts.
Include 10-15 flashcards with:
1. Term/Question on front
2. Definition/Answer on back
Format as structured JSON with keys: title, cards (array with front, back).""",
}


@router.post("/generate", response_model=GenerateResponse)
async def generate_content(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = await db.get(Book, req.book_id)
    if not book or book.user_id != user.id:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status != "ready":
        raise HTTPException(status_code=400, detail="Book is still processing")

    if req.content_type not in PROMPTS:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {req.content_type}")

    chunks = await retrieve_relevant_chunks(db, req.book_id, req.content_type, top_k=8, chapter_id=req.chapter_id)
    context = "\n\n---\n\n".join(c["content"] for c in chunks)

    generation_prompt = PROMPTS[req.content_type]
    if req.topic:
        generation_prompt += f"\n\nFocus specifically on: {req.topic}"
    if req.grade_level:
        generation_prompt += f"\n\nTarget grade level: {req.grade_level}"
    if req.additional_instructions:
        generation_prompt += f"\n\nAdditional instructions: {req.additional_instructions}"

    user_message = f"""BOOK EXCERPTS:
{context}

TASK:
{generation_prompt}

Respond ONLY with valid JSON. No markdown, no explanations."""

    response = await llm_gateway.chat(
        messages=[
            {"role": "system", "content": "You are an AI education content generator. Output ONLY valid JSON."},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    try:
        content_json = json.loads(response.content)
    except json.JSONDecodeError:
        content_json = {"raw": response.content, "title": req.content_type.replace("_", " ").title()}

    generated = GeneratedContent(
        user_id=user.id,
        book_id=req.book_id,
        content_type=req.content_type,
        title=content_json.get("title", req.content_type.replace("_", " ").title()),
        content=content_json,
    )
    db.add(generated)
    await db.flush()

    return GenerateResponse(
        content_id=generated.id,
        content_type=req.content_type,
        title=generated.title,
        content=content_json,
    )
