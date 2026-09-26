from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    email: str
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(default="teacher")


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class BookResponse(BaseModel):
    id: str
    title: str
    author: Optional[str]
    total_pages: int
    total_chunks: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class BookUploadResponse(BaseModel):
    book_id: str
    message: str
    status: str


class ChapterResponse(BaseModel):
    id: str
    book_id: str
    title: str
    order: int
    start_page: int
    end_page: int

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    book_id: str
    question: str
    session_id: Optional[str] = None
    chapter_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    sources: list[dict] = []
    provider: str
    model: str
    tokens_used: int
    response_time_ms: int


class ChatSessionResponse(BaseModel):
    id: str
    book_id: str
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GenerateRequest(BaseModel):
    book_id: str
    content_type: str
    topic: Optional[str] = None
    grade_level: Optional[str] = None
    additional_instructions: Optional[str] = None
    chapter_id: Optional[str] = None


class GenerateResponse(BaseModel):
    content_id: str
    content_type: str
    title: str
    content: dict


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None
