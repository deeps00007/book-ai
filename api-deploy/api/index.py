import os

os.environ["USE_SQLITE"] = "false"
os.environ["ENVIRONMENT"] = "production"
os.environ["DATABASE_URL"] = "postgresql://postgres.ynltzrdihjycufniyvlk:SupabaseDBPassword1!@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
os.environ["SUPABASE_URL"] = "https://ynltzrdihjycufniyvlk.supabase.co"
os.environ["SUPABASE_SERVICE_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlubHR6cmRpaGp5Y3Vmbml5dmxrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NjAwNDk2NywiZXhwIjoyMTAxNTgwOTY3fQ.GtLiYfGEvHeuhH39acrbOiTEnQ4WIEZ4uQHVwLvQvhE"
os.environ.setdefault("FIREWORKS_API_KEY", "fw_URSNoRJPREb9orbdGzC23N")
os.environ.setdefault("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")

from app.main import app
from sqlalchemy import text
from app.core.database import engine


@app.get("/dbcheck")
async def dbcheck():
    result = {"url": os.environ.get("DATABASE_URL", "NOT SET")[:50]}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            result["db"] = "ok"
    except Exception as e:
        result["db"] = f"{type(e).__name__}: {str(e)[:200]}"
    return result
