import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Integer, Float, JSON, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# Try importing pgvector for PostgreSQL mode; skip for SQLite
try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False

from app.core.config import settings


def new_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="teacher")
    school_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("schools.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    school = relationship("School", back_populates="users")
    books = relationship("Book", back_populates="owner")
    chat_sessions = relationship("ChatSession", back_populates="user")


class School(Base):
    __tablename__ = "schools"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_plan: Mapped[str] = mapped_column(String(50), default="free")
    credits_remaining: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    users = relationship("User", back_populates="school")


class Book(Base):
    __tablename__ = "books"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="uploading")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="books")
    chapters = relationship("Chapter", back_populates="book", order_by="Chapter.order")
    chunks = relationship("BookChunk", back_populates="book")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    start_page: Mapped[int] = mapped_column(Integer, default=0)
    end_page: Mapped[int] = mapped_column(Integer, default=0)

    book = relationship("Book", back_populates="chapters")


class BookChunk(Base):
    __tablename__ = "book_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id"), nullable=False, index=True)
    chapter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("chapters.id"), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_start: Mapped[int] = mapped_column(Integer, default=0)
    page_end: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    book = relationship("Book", back_populates="chunks")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), default="New Chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", order_by="ChatMessage.created_at")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    response_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(50), nullable=False)
    credits_total: Mapped[int] = mapped_column(Integer, default=100)
    credits_used: Mapped[int] = mapped_column(Integer, default=0)
    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    starts_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GeneratedContent(Base):
    __tablename__ = "generated_content"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id"), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class APIUsageLog(Base):
    __tablename__ = "api_usage_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    response_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
