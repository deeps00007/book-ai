import asyncio
import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import get_settings
from app.workers.celery_app import celery_app
from app.services.upload_service import process_book

settings = get_settings()
logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.upload_worker.process_book_task")
def process_book_task(book_id: str, file_path: str, title: str):
    async def _process():
        async with async_session() as db:
            try:
                result = await process_book(file_path, title)
                chunks = result["chunks"]

                embedding_dim = settings.embedding_dimension
                for chunk in chunks:
                    emb = chunk.get("embedding")
                    if emb and len(emb) == embedding_dim:
                        embedding_str = f"[{','.join(str(x) for x in emb)}]"
                    else:
                        embedding_str = None

                    await db.execute(
                        text("""
                            INSERT INTO book_chunks (id, book_id, chunk_index, content, embedding, page_start, page_end)
                            VALUES (gen_random_uuid(), :book_id, :chunk_index, :content, :embedding::vector, :page_start, :page_end)
                        """),
                        {
                            "book_id": book_id,
                            "chunk_index": chunk["index"],
                            "content": chunk["text"],
                            "embedding": embedding_str,
                            "page_start": 0,
                            "page_end": 0,
                        },
                    )

                await db.execute(
                    text("UPDATE books SET status = 'ready', total_chunks = :total, total_pages = :pages WHERE id = :id"),
                    {"total": result["total_chunks"], "pages": result["total_pages"], "id": book_id},
                )
                await db.commit()
                logger.info(f"Book {book_id} processed: {result['total_chunks']} chunks")
            except Exception as e:
                await db.rollback()
                await db.execute(
                    text("UPDATE books SET status = 'failed', error_message = :msg WHERE id = :id"),
                    {"msg": str(e), "id": book_id},
                )
                await db.commit()
                logger.error(f"Book {book_id} failed: {e}")
                raise

    return _run_async(_process())


def trigger_book_processing(book_id: str, file_path: str, title: str):
    process_book_task.delay(book_id, file_path, title)
