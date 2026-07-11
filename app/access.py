from __future__ import annotations

from app.config import Settings


def is_admin(user_id: int, settings: Settings) -> bool:
    return settings.admin_user_id is not None and user_id == settings.admin_user_id


def access_denied_message(user_id: int) -> str:
    return (
        "У вас пока нет доступа к этому боту.\n\n"
        f"Ваш Telegram ID: {user_id}\n"
        "Я уже отправил заявку администратору."
    )
