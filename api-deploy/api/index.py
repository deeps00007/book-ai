import os

os.environ.setdefault("USE_SQLITE", "false")
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres.ynltzrdihjycufniyvlk:SupabaseDBPassword1!@aws-0-ap-south-1.pooler.supabase.com:6543/postgres",
)
os.environ.setdefault("SUPABASE_URL", "https://ynltzrdihjycufniyvlk.supabase.co")
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlubHR6cmRpaGp5Y3Vmbml5dmxrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NjAwNDk2NywiZXhwIjoyMTAxNTgwOTY3fQ.GtLiYfGEvHeuhH39acrbOiTEnQ4WIEZ4uQHVwLvQvhE",
)

from app.main import app
