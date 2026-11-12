import os
import re
import secrets
from functools import wraps

from flask import (
    Flask, abort, flash, g, jsonify, redirect, render_template,
    request, session, url_for,
)
from flask_login import (
    LoginManager, current_user, login_required, login_user, logout_user,
)
from slugify import slugify
from sqlalchemy import func
from werkzeug.utils import secure_filename

from config import Config
from models import Comment, Post, SiteSettings, User, Visit, db

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Войдите, чтобы продолжить."
login_manager.login_message_category = "warning"

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# -------------------- User loader --------------------

@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


# -------------------- Декораторы --------------------

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login", next=request.path))
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# -------------------- Учёт посещений --------------------

@app.before_request
def track_visit():
    if request.endpoint in ("static",) or request.path.startswith("/static/"):
        return
    token = session.get("visit_token")
    if not token:
        token = secrets.token_hex(16)
        session["visit_token"] = token
        db.session.add(Visit(
            session_token=token,
            user_id=current_user.id if current_user.is_authenticated else None,
            ip=request.headers.get("X-Forwarded-For", request.remote_addr or "")[:64],
            user_agent=(request.headers.get("User-Agent") or "")[:300],
        ))
        db.session.commit()
    else:
        v = Visit.query.filter_by(session_token=token).first()
        if v:
            v.last_seen = func.now()
            if current_user.is_authenticated and v.user_id is None:
                v.user_id = current_user.id
            db.session.commit()


@app.context_processor
def inject_settings():
    try:
        s = SiteSettings.get()
    except Exception:
        s = None
    return {"site": s}


# -------------------- Утилиты --------------------

def unique_slug(title: str, exclude_id: int | None = None) -> str:
    base = slugify(title) or "post"
    base = re.sub(r"[^a-z0-9-]+", "-", base).strip("-") or "post"
    slug = base
    counter = 2
    while True:
        q = Post.query.filter_by(slug=slug)
        if exclude_id:
            q = q.filter(Post.id != exclude_id)
        if not q.first():
            return slug
        slug = f"{base}-{counter}"
        counter += 1


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


# -------------------- Публичные маршруты --------------------

@app.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    pagination = (
        Post.query.filter_by(is_published=True)
        .order_by(Post.created_at.desc())
        .paginate(page=page, per_page=app.config["POSTS_PER_PAGE"], error_out=False)
    )
    return render_template("index.html", posts=pagination.items, pagination=pagination)


@app.route("/post/<slug>")
def post_detail(slug: str):
    post = Post.query.filter_by(slug=slug).first_or_404()
    if not post.is_published and not (current_user.is_authenticated and current_user.is_admin):
        abort(404)
    post.views = (post.views or 0) + 1
    db.session.commit()
    return render_template("post.html", post=post)


@app.route("/post/<slug>/comment", methods=["POST"])
@login_required
def add_comment(slug: str):
    post = Post.query.filter_by(slug=slug).first_or_404()
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Комментарий пустой.", "error")
    elif len(body) > 2000:
        flash("Слишком длинный комментарий (макс. 2000).", "error")
    else:
        db.session.add(Comment(body=body, post_id=post.id, author_id=current_user.id))
        db.session.commit()
        flash("Комментарий добавлен.", "success")
    return redirect(url_for("post_detail", slug=slug))


# -------------------- Загрузка файлов --------------------

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "Файл не передан"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "Пустое имя файла"}), 400
    if not allowed_file(f.filename):
        return jsonify({"error": "Недопустимый формат"}), 400

    name = secure_filename(f.filename)
    stem, ext = os.path.splitext(name)
    uniq = f"{stem[:60]}-{secrets.token_hex(4)}{ext}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], uniq)
    f.save(path)
    url = url_for("static", filename=f"uploads/{uniq}")
    return jsonify({"url": url})


# -------------------- Аутентификация --------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        ident = (request.form.get("identifier") or "").strip().lower()
        pwd = request.form.get("password") or ""
        user = User.query.filter(
            (func.lower(User.username) == ident) | (func.lower(User.email) == ident)
        ).first()
        if user and user.check_password(pwd):
            login_user(user, remember=bool(request.form.get("remember")))
            nxt = request.args.get("next") or url_for("index")
            if not nxt.startswith("/"):
                nxt = url_for("index")
            return redirect(nxt)
        flash("Неверный логин или пароль.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        pwd = request.form.get("password") or ""
        pwd2 = request.form.get("password2") or ""

        errors = []
        if len(username) < 3:
            errors.append("Имя — от 3 символов.")
        if "@" not in email:
            errors.append("Некорректный e-mail.")
        if len(pwd) < 6:
            errors.append("Пароль — от 6 символов.")
        if pwd != pwd2:
            errors.append("Пароли не совпадают.")
        if User.query.filter(func.lower(User.username) == username.lower()).first():
            errors.append("Имя занято.")
        if User.query.filter(func.lower(User.email) == email).first():
            errors.append("E-mail занят.")

        if errors:
            for e in errors:
                flash(e, "error")
        else:
            u = User(username=username, email=email, is_admin=False)
            u.set_password(pwd)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            flash("Регистрация успешна.", "success")
            return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли.", "success")
    return redirect(url_for("index"))


# -------------------- Профиль --------------------

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "password":
            old = request.form.get("old_password") or ""
            new = request.form.get("new_password") or ""
            new2 = request.form.get("new_password2") or ""
            if not current_user.check_password(old):
                flash("Текущий пароль неверен.", "error")
            elif len(new) < 6:
                flash("Новый пароль — от 6 символов.", "error")
            elif new != new2:
                flash("Пароли не совпадают.", "error")
            else:
                current_user.set_password(new)
                db.session.commit()
                flash("Пароль изменён.", "success")
        elif action == "email":
            email = (request.form.get("email") or "").strip().lower()
            if "@" not in email:
                flash("Некорректный e-mail.", "error")
            elif User.query.filter(func.lower(User.email) == email, User.id != current_user.id).first():
                flash("E-mail уже занят.", "error")
            else:
                current_user.email = email
                db.session.commit()
                flash("E-mail обновлён.", "success")
    return render_template("profile.html")


# -------------------- Дашборд --------------------

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_admin:
        posts = Post.query.order_by(Post.created_at.desc()).all()
    else:
        posts = Post.query.filter_by(author_id=current_user.id).order_by(Post.created_at.desc()).all()
    return render_template("dashboard.html", posts=posts)


@app.route("/dashboard/new", methods=["GET", "POST"])
@login_required
def new_post():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        summary = (request.form.get("summary") or "").strip()
        content = request.form.get("content") or ""
        cover = (request.form.get("cover_url") or "").strip()
        is_pub = bool(request.form.get("is_published"))

        if not title or not content.strip():
            flash("Заголовок и текст обязательны.", "error")
        else:
            p = Post(
                title=title,
                slug=unique_slug(title),
                summary=summary[:300],
                content=content,
                cover_url=cover[:400],
                is_published=is_pub,
                author_id=current_user.id,
            )
            db.session.add(p)
            db.session.commit()
            flash("Пост создан.", "success")
            return redirect(url_for("dashboard"))
    return render_template("edit_post.html", post=None)


@app.route("/dashboard/edit/<int:post_id>", methods=["GET", "POST"])
@login_required
def edit_post(post_id: int):
    post = db.session.get(Post, post_id) or abort(404)
    if not current_user.is_admin and post.author_id != current_user.id:
        abort(403)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        content = request.form.get("content") or ""
        if not title or not content.strip():
            flash("Заголовок и текст обязательны.", "error")
        else:
            post.title = title
            post.summary = (request.form.get("summary") or "").strip()[:300]
            post.content = content
            post.cover_url = (request.form.get("cover_url") or "").strip()[:400]
            post.is_published = bool(request.form.get("is_published"))
            db.session.commit()
            flash("Изменения сохранены.", "success")
            return redirect(url_for("dashboard"))
    return render_template("edit_post.html", post=post)


@app.route("/dashboard/delete/<int:post_id>", methods=["POST"])
@login_required
def delete_post(post_id: int):
    post = db.session.get(Post, post_id) or abort(404)
    if not current_user.is_admin and post.author_id != current_user.id:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash("Пост удалён.", "success")
    return redirect(url_for("dashboard"))


# -------------------- Настройки сайта (только админ) --------------------

@app.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    s = SiteSettings.get()
    if request.method == "POST":
        s.site_title = (request.form.get("site_title") or "").strip()[:120] or "Блог"
        s.site_tagline = (request.form.get("site_tagline") or "").strip()[:200]
        s.accent_color = (request.form.get("accent_color") or "").strip()[:20] or "#f15a22"
        s.footer_text = (request.form.get("footer_text") or "").strip()[:300]
        s.show_visitor_counter = bool(request.form.get("show_visitor_counter"))
        db.session.commit()
        flash("Настройки сохранены.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", s=s)


# -------------------- Статистика (только админ) --------------------

@app.route("/stats")
@admin_required
def stats():
    total_visits = Visit.query.count()
    total_users = User.query.count()
    logged_visits = Visit.query.filter(Visit.user_id.isnot(None)).count()
    posts_total = Post.query.count()
    comments_total = Comment.query.count()
    views_total = db.session.query(func.coalesce(func.sum(Post.views), 0)).scalar()

    recent = Visit.query.order_by(Visit.first_seen.desc()).limit(30).all()
    return render_template(
        "stats.html",
        total_visits=total_visits,
        total_users=total_users,
        logged_visits=logged_visits,
        posts_total=posts_total,
        comments_total=comments_total,
        views_total=views_total,
        recent=recent,
    )


# -------------------- Ошибки --------------------

@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


# -------------------- Создание БД при первом импорте --------------------

with app.app_context():
    db.create_all()
    SiteSettings.get()

    # Автосоздание администратора lilia / kuramshina при первом запуске
    if not User.query.filter_by(username="lilia").first():
        admin = User(
            username="lilia",
            email="lilia@example.com",
            is_admin=True,
        )
        admin.set_password("kuramshina")
        db.session.add(admin)
        db.session.commit()
        print("Создан администратор: lilia / kuramshina")
    else:
        print("Пользователь lilia уже существует.")


if __name__ == "__main__":
    app.run(debug=True)