from app import app
from models import SiteSettings, User, db

with app.app_context():
    db.create_all()

    # Настройки сайта — гарантированно существуют
    SiteSettings.get()

    # Первый пользователь — lilia / kuramshina — админ
    if not User.query.filter_by(username="lilia").first():
        lilia = User(
            username="lilia",
            email="lilia@example.com",
            is_admin=True,
        )
        lilia.set_password("kuramshina")
        db.session.add(lilia)
        db.session.commit()
        print("Создан администратор: lilia / kuramshina")
    else:
        print("Пользователь lilia уже существует — пропущено.")