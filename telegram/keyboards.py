from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def download_confirmation_keyboard(task_id: str, is_album_or_photo: bool = False) -> InlineKeyboardMarkup:
    if is_album_or_photo:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📥 Скачать публикацию / альбом",
                        callback_data=f"dl:{task_id}:post",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data=f"cancel_download:{task_id}",
                    ),
                ],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎬 720p HD",
                    callback_data=f"dl:{task_id}:720",
                ),
                InlineKeyboardButton(
                    text="🌟 1080p FHD",
                    callback_data=f"dl:{task_id}:1080",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📱 480p",
                    callback_data=f"dl:{task_id}:480",
                ),
                InlineKeyboardButton(
                    text="🎵 Аудио (MP3)",
                    callback_data=f"dl:{task_id}:audio",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"cancel_download:{task_id}",
                ),
            ],
        ]
    )


def mode_settings_keyboard(quick_mode: bool) -> InlineKeyboardMarkup:
    status_text = "⚡ Быстрый (без подтверждения)" if quick_mode else "📋 Обычный (с превью и выбором)"
    btn_action = "Переключить на Обычный" if quick_mode else "Переключить на Быстрый"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔄 {btn_action}",
                    callback_data="toggle_quick_mode",
                )
            ]
        ]
    )


def compression_confirmation_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, сжать",
                    callback_data=f"confirm_compress:{task_id}",
                ),
                InlineKeyboardButton(
                    text="Нет",
                    callback_data=f"cancel_compress:{task_id}",
                ),
            ]
        ]
    )


def document_fallback_confirmation_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, подготовить файл",
                    callback_data=f"confirm_compress:{task_id}",
                ),
                InlineKeyboardButton(
                    text="Нет",
                    callback_data=f"cancel_compress:{task_id}",
                ),
            ]
        ]
    )
