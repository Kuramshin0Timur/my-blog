import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-please")

    # Render передаёт DATABASE_URL (внутренний URL PostgreSQL)
    # Локально, если переменной нет — SQLite
    _db_url = os.environ.get("DATABASE_URL")

    if _db_url:
        # Render иногда отдаёт postgres:// — SQLAlchemy 2.x требует postgresql://
        if _db_url.startswith("postgres://"):
            _db_url = _db_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = _db_url
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "blog.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    POSTS_PER_PAGE = 5

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
    ALLOWED_EXTENSIONS = {
        "png", "jpg", "jpeg", "gif", "webp", "svg",
        "mp4", "webm", "mov", "ogg",
    }