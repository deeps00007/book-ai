from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

if settings.use_sqlite or not settings.database_url:
    db_url = f"sqlite+aiosqlite:///{settings.sqlite_path}"
    conn_args = {"check_same_thread": False}
    engine = create_async_engine(db_url, echo=False, connect_args=conn_args)
else:
    engine = create_async_engine(
        settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
        echo=False,
        pool_size=10,
        max_overflow=5,
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
