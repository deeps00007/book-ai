import os

# Non-secret runtime flags (safe to commit).
# All secrets (DATABASE_URL, GOOGLE_*, SUPABASE_*, FIREWORKS_*) come from
# Vercel environment variables — never hardcoded here.
os.environ.setdefault("USE_SQLITE", "false")
os.environ.setdefault("ENVIRONMENT", "production")

from app.main import app
from sqlalchemy import text
from app.core.database import engine


@app.get("/dbcheck")
async def dbcheck():
    result = {"configured": bool(os.environ.get("DATABASE_URL"))}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            result["db"] = "ok"
    except Exception as e:
        result["db"] = f"{type(e).__name__}: {str(e)[:150]}"
    return result
