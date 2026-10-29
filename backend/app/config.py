import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # creativeflow/


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{ROOT / 'backend' / 'creativeflow.db'}"
    )
    STORAGE_DIR = os.environ.get("STORAGE_DIR", str(ROOT / "storage" / "private"))
    # Public base URL used when building review/delivery links for WhatsApp.
    PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:5173").rstrip("/")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024
    FRONTEND_DIST = os.environ.get("FRONTEND_DIST", str(ROOT / "frontend" / "dist"))

    # Test installs only: lets anyone create their own account from the sign-in page. Off unless DEMO_SIGNUP=1.
    DEMO_SIGNUP = os.environ.get("DEMO_SIGNUP", "0") == "1"

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7

    # Signed download links live this long (seconds) once issued.
    DOWNLOAD_LINK_TTL = 300
