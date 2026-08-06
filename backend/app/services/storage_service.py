import os
import uuid
import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ynltzrdihjycufniyvlk.supabase.co")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BUCKET = "books"


async def upload_book_async(file_content: bytes, filename: str) -> tuple[str, str]:
    """Upload a file to Supabase Storage. Returns (public_url, storage_path)."""
    safe_name = f"{uuid.uuid4()}_{filename}"
    path = f"books/{safe_name}"

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/pdf",
        "x-upsert": "false",
    }

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/storage/v1/object/{path}",
            content=file_content,
            headers=headers,
        )
        resp.raise_for_status()

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{path}"
    return public_url, path


def upload_book_sync(file_content: bytes, filename: str) -> tuple[str, str]:
    """Synchronous wrapper for environments without a running loop."""
    import asyncio
    return asyncio.run(upload_book_async(file_content, filename))
