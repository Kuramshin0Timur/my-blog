import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-please")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "blog.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    POSTS_PER_PAGE = 5

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 МБ на файл
    ALLOWED_EXTENSIONS = {
        "png", "jpg", "jpeg", "gif", "webp", "svg",
        "mp4", "webm", "mov", "ogg",
    }