from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pydantic import BaseModel, Field
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User, Book
from app.services.test_paper_service import generate_test_paper_questions, build_test_paper_pdf

router = APIRouter()


class QuestionTypeItem(BaseModel):
    type: str
    label: str
    count: int = Field(..., ge=1, le=50)
    marks_per: int = Field(..., ge=1, le=20)


class TestPaperRequest(BaseModel):
    book_id: str
    chapter_ids: list[str] = []
    school_name: str = Field(..., min_length=1)
    class_name: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    duration: str = Field(..., min_length=1)
    question_types: list[QuestionTypeItem]
    topic: Optional[str] = ""


@router.post("/test-paper")
async def generate_test_paper(
    req: TestPaperRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = await db.get(Book, req.book_id)
    if not book or book.user_id != user.id:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.status != "ready":
        raise HTTPException(status_code=400, detail="Book is still processing")

    question_types = [qt.model_dump() for qt in req.question_types]
    if not question_types:
        raise HTTPException(status_code=400, detail="At least one question type required")

    data = await generate_test_paper_questions(
        db=db,
        book_id=req.book_id,
        chapter_ids=req.chapter_ids,
        school_name=req.school_name,
        class_name=req.class_name,
        subject=req.subject,
        duration=req.duration,
        question_types=question_types,
        topic=req.topic or "",
    )

    pdf_bytes = build_test_paper_pdf(data)

    safe_subject = req.subject.replace(" ", "_").replace("/", "-")
    filename = f"Test_Paper_{safe_subject}_{req.class_name.replace(' ', '_')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
