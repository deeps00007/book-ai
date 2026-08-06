import os

os.environ.setdefault("USE_SQLITE", "false")
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres.ynltzrdihjycufniyvlk:SupabaseDBPassword1!@aws-0-ap-south-1.pooler.supabase.com:6543/postgres",
)

from app.main import app
