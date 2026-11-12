from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship("Post", backref="author", lazy=True)
    comments = db.relationship("Comment", backref="author", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    summary = db.Column(db.String(300), nullable=False, default="")
    content = db.Column(db.Text, nullable=False)           # HTML из WYSIWYG
    cover_url = db.Column(db.String(400), default="")       # обложка (URL)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    views = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    comments = db.relationship(
        "Comment", backref="post", lazy=True, cascade="all, delete-orphan"
    )


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class SiteSettings(db.Model):
    """Единственная строка (id=1) с настройками сайта."""
    __tablename__ = "site_settings"

    id = db.Column(db.Integer, primary_key=True)
    site_title = db.Column(db.String(120), default="Блог")
    site_tagline = db.Column(db.String(200), default="Личный блог")
    accent_color = db.Column(db.String(20), default="#f15a22")
    footer_text = db.Column(db.String(300), default="© 2026 Блог одного автора")
    show_visitor_counter = db.Column(db.Boolean, default=True)

    @staticmethod
    def get():
        s = db.session.get(SiteSettings, 1)
        if s is None:
            s = SiteSettings(id=1)
            db.session.add(s)
            db.session.commit()
        return s


class Visit(db.Model):
    """Одна запись = один визит (сессия)."""
    __tablename__ = "visits"

    id = db.Column(db.Integer, primary_key=True)
    session_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    ip = db.Column(db.String(64), default="")
    user_agent = db.Column(db.String(300), default="")
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)