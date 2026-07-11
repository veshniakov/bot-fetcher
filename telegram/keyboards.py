from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def download_confirmation_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, скачать",
                    callback_data=f"confirm_download:{task_id}",
                ),
                InlineKeyboardButton(
                    text="Нет",
                    callback_data=f"cancel_download:{task_id}",
                ),
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


def access_request_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Разрешить",
                    callback_data=f"approve_user:{user_id}",
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"reject_user:{user_id}",
                ),
            ]
        ]
    )
