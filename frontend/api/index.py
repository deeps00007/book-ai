import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["USE_SQLITE"] = "true"
os.environ["SQLITE_PATH"] = "/tmp/bookai.db"
os.environ["UPLOAD_DIR"] = "/tmp/uploads"
os.environ["ENVIRONMENT"] = "production"

from backend.app.main import app as application