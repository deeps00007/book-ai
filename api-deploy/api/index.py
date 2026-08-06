import os

os.environ.setdefault("USE_SQLITE", "true")
os.environ.setdefault("SQLITE_PATH", "/tmp/bookai.db")
os.environ.setdefault("UPLOAD_DIR", "/tmp/uploads")
os.environ.setdefault("ENVIRONMENT", "production")

from app.main import app
