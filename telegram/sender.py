from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, Message

from telegram.captions import build_preview_caption, build_video_caption, split_plain_text_as_html
from telegram.keyboards import download_confirmation_keyboard
from utils.shell import CommandError, run_command
from video.metadata import VideoMetadata

logger = logging.getLogger(__name__)


async def send_preview(message: Message, metadata: VideoMetadata, task_id: str) -> None:
    caption = build_preview_caption(metadata)
    keyboard = download_confirmation_keyboard(task_id)
    if metadata.thumbnail:
        try:
            await message.answer_photo(
                photo=metadata.thumbnail,
                caption=caption,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            return
        except TelegramBadRequest:
            logger.info("Telegram rejected preview thumbnail, falling back to text")

    await message.answer(caption, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def send_video_result(
    bot: Bot,
    *,
    chat_id: int,
    file_path: Path,
    metadata: VideoMetadata,
    use_file_uri: bool = False,
) -> None:
    caption, extra_description = build_video_caption(metadata)
    video = _file_uri(file_path) if use_file_uri else FSInputFile(file_path)
    kwargs = {
        "chat_id": chat_id,
        "video": video,
        "caption": caption,
        "parse_mode": ParseMode.HTML,
        "supports_streaming": True,
    }

    try:
        await bot.send_video(**kwargs, show_caption_above_media=True)
    except TypeError:
        await bot.send_video(**kwargs)

    if extra_description:
        for chunk in split_plain_text_as_html(extra_description):
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )


async def send_document_result(
    bot: Bot,
    *,
    chat_id: int,
    file_path: Path,
    metadata: VideoMetadata,
    use_file_uri: bool = False,
) -> None:
    caption, extra_description = build_video_caption(metadata)
    thumbnail_path = await _make_document_thumbnail(file_path)

    kwargs = {
        "chat_id": chat_id,
        "document": _file_uri(file_path) if use_file_uri else FSInputFile(file_path),
        "caption": caption,
        "parse_mode": ParseMode.HTML,
    }
    if thumbnail_path:
        kwargs["thumbnail"] = FSInputFile(thumbnail_path)

    try:
        await bot.send_document(**kwargs)
    except TelegramBadRequest:
        if thumbnail_path:
            logger.info("Telegram rejected document thumbnail, sending without thumbnail")
            kwargs.pop("thumbnail", None)
            await bot.send_document(**kwargs)
        else:
            raise

    if extra_description:
        for chunk in split_plain_text_as_html(extra_description):
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )


async def _make_document_thumbnail(file_path: Path) -> Path | None:
    thumbnail_path = file_path.with_name(f"{file_path.stem}.thumb.jpg")
    try:
        await run_command(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "00:00:01",
                "-i",
                str(file_path),
                "-frames:v",
                "1",
                "-vf",
                "scale=min(320\\,iw):-2",
                "-q:v",
                "5",
                str(thumbnail_path),
            ],
            timeout=30,
        )
    except (CommandError, TimeoutError):
        logger.info("Failed to generate document thumbnail", exc_info=True)
        return None

    if not thumbnail_path.exists() or thumbnail_path.stat().st_size > 200 * 1024:
        thumbnail_path.unlink(missing_ok=True)
        return None
    return thumbnail_path


def _file_uri(file_path: Path) -> str:
    return file_path.resolve().as_uri()
