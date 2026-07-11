from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.access import access_denied_message, is_admin
from app.access_store import AccessStore
from app.config import Settings
from app.tasks import (
    CANCELLED,
    COMPLETED,
    DOWNLOADING,
    FAILED,
    SENDING,
    WAITING_DOWNLOAD_CONFIRMATION,
    PendingTask,
    PendingTaskStore,
)
from downloader.base import (
    DownloadError,
    InstagramAuthError,
    InvalidUrlError,
    MetadataError,
    UnsupportedStoryUrlError,
    UnsupportedUrlError,
)
from downloader.instagram_story_downloader import InstagramStoryDownloader
from downloader.platform_detector import SUPPORTED_MESSAGE, detect_platform
from downloader.ytdlp_downloader import YtDlpDownloader
from storage.paths import create_task_work_dir, file_size, remove_task_work_dir
from telegram.keyboards import access_request_keyboard
from telegram.sender import send_preview, send_video_result
from utils.formatting import format_size, url_domain
from video.metadata import VideoMetadata

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
QUALITY_FALLBACKS = [720, 480, 360]

BROKEN_LINK_MESSAGE = "Не удалось распознать ссылку."
NO_METADATA_MESSAGE = (
    "Не удалось получить информацию о видео. Возможно, ссылка приватная "
    "или сервис временно ограничил доступ."
)
DOWNLOAD_FAILED_MESSAGE = (
    "Не удалось получить видео. Возможно, ссылка приватная или сервис временно ограничил доступ."
)
TOO_LARGE_MESSAGE = (
    "Не удалось подобрать версию видео, которая помещается в лимит Telegram Bot API Server."
)
INTERNAL_ERROR_MESSAGE = "Произошла ошибка при обработке ссылки."
INSTAGRAM_USER_AUTH_MESSAGE = (
    "Не удалось получить Instagram-видео. Возможно, нужна повторная авторизация Instagram."
)
INSTAGRAM_ADMIN_AUTH_MESSAGE = (
    "Instagram-сессия устарела или недоступна. Нужно обновить cookies/session на сервере."
)
SPECIFIC_STORY_REQUIRED_MESSAGE = (
    "Для Instagram Stories в MVP нужна ссылка на конкретную Story, а не общий профиль/stories."
)


def create_router(
    settings: Settings,
    store: PendingTaskStore,
    access_store: AccessStore,
) -> Router:
    router = Router()

    @router.message(Command("id"))
    async def id_command(message: Message) -> None:
        if message.from_user is None:
            return
        await message.answer(f"Ваш Telegram ID: {message.from_user.id}")

    @router.message(Command("allow"))
    async def allow_command(message: Message, bot: Bot) -> None:
        if not await _ensure_admin(message, settings):
            return
        user_id = _parse_user_id_argument(message.text or "")
        if user_id is None:
            await message.answer("Использование: /allow <telegram_id>")
            return
        changed = await access_store.add_user(user_id)
        if changed:
            await message.answer(f"Пользователь {user_id} добавлен в whitelist.")
            await _safe_send(bot=bot, chat_id=user_id, text="Администратор выдал вам доступ к боту.")
        else:
            await message.answer(f"Пользователь {user_id} уже есть в whitelist.")

    @router.message(Command("deny"))
    async def deny_command(message: Message) -> None:
        if not await _ensure_admin(message, settings):
            return
        user_id = _parse_user_id_argument(message.text or "")
        if user_id is None:
            await message.answer("Использование: /deny <telegram_id>")
            return
        if settings.admin_user_id == user_id:
            await message.answer("Администратора нельзя удалить из whitelist.")
            return
        changed = await access_store.remove_user(user_id)
        if changed:
            await message.answer(f"Пользователь {user_id} удалён из whitelist.")
        else:
            await message.answer(f"Пользователя {user_id} не было в whitelist.")

    @router.message(Command("users"))
    async def users_command(message: Message) -> None:
        if not await _ensure_admin(message, settings):
            return
        users = await access_store.list_users()
        if not users:
            await message.answer("Whitelist пуст.")
            return
        lines = ["Whitelist:"] + [str(user_id) for user_id in users]
        await message.answer("\n".join(lines))

    @router.message(Command("start"))
    async def start_command(message: Message, bot: Bot) -> None:
        if not await _ensure_allowed_message(message, bot, settings, access_store):
            return
        await message.answer(
            "Отправьте ссылку на YouTube или Instagram, а я попробую скачать видео "
            "и прислать его сюда."
        )

    @router.message(Command("help"))
    async def help_command(message: Message, bot: Bot) -> None:
        if not await _ensure_allowed_message(message, bot, settings, access_store):
            return
        await message.answer(
            "Поддерживаются YouTube, YouTube Shorts, Instagram Reels, Instagram posts "
            "и Instagram Stories.\n\n"
            "Сначала я покажу preview: название, источник, автора, длительность и размер, "
            "если он известен. Скачивание начнётся только после подтверждения.\n\n"
            "Бот скачивает готовую версию до 720p и отправляет её через локальный "
            "Telegram Bot API Server. Если 720p-файл окажется слишком большим, "
            "я попробую готовые варианты 480p и 360p без перекодирования.\n\n"
            "Instagram Stories могут требовать актуальную Instagram-сессию на сервере."
        )

    @router.message(F.text)
    async def link_message(message: Message, bot: Bot) -> None:
        if message.from_user is None:
            return
        if not await _ensure_allowed_message(message, bot, settings, access_store):
            return

        user_id = message.from_user.id
        chat_id = message.chat.id
        url = _extract_first_url(message.text or "")
        if not url:
            await message.answer(BROKEN_LINK_MESSAGE)
            return

        if await store.has_active_task(user_id):
            await message.answer("У вас уже есть активная задача. Сначала завершите её или отмените.")
            return

        try:
            detected = detect_platform(url)
        except InvalidUrlError:
            await message.answer(BROKEN_LINK_MESSAGE)
            return
        except UnsupportedStoryUrlError:
            await message.answer(SPECIFIC_STORY_REQUIRED_MESSAGE)
            return
        except UnsupportedUrlError:
            await message.answer(SUPPORTED_MESSAGE)
            return

        task = await store.create(
            user_id=user_id,
            chat_id=chat_id,
            url=url,
            platform=detected.platform,
            content_type=detected.content_type,
        )
        work_dir = create_task_work_dir(settings, task.task_id)
        await store.update(
            task.task_id,
            work_dir=work_dir,
            context={
                "domain": detected.domain,
                "story_username": detected.story_username,
                "story_id": detected.story_id,
            },
        )

        await message.answer("Получаю информацию о видео...")
        downloader = _downloader_for_task(settings, task)

        try:
            metadata = await downloader.get_metadata(url)
            await store.update(task.task_id, metadata=metadata)
            logger.info(
                "metadata_ok user_id=%s platform=%s content_type=%s domain=%s duration=%s estimated_size=%s status=%s",
                user_id,
                detected.platform,
                detected.content_type,
                detected.domain,
                metadata.duration,
                metadata.estimated_filesize,
                WAITING_DOWNLOAD_CONFIRMATION,
            )
            await send_preview(message, metadata, task.task_id)
        except UnsupportedUrlError:
            await _remove_task(task, store, settings, FAILED)
            await message.answer(SUPPORTED_MESSAGE)
        except InstagramAuthError:
            await _remove_task(task, store, settings, FAILED)
            await _notify_instagram_auth_problem(bot, settings)
            await message.answer(INSTAGRAM_USER_AUTH_MESSAGE)
        except MetadataError:
            await _remove_task(task, store, settings, FAILED)
            await message.answer(NO_METADATA_MESSAGE)
        except Exception:
            logger.exception("Unhandled metadata error for user_id=%s domain=%s", user_id, detected.domain)
            await _remove_task(task, store, settings, FAILED)
            await message.answer(INTERNAL_ERROR_MESSAGE)

    @router.callback_query(F.data.startswith("approve_user:"))
    async def approve_user_callback(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id, settings):
            await callback.answer("Только администратор может выдавать доступ.", show_alert=True)
            return
        user_id = _parse_callback_user_id(callback.data)
        if user_id is None:
            await callback.answer("Некорректная заявка.", show_alert=True)
            return
        await access_store.add_user(user_id)
        await callback.answer("Доступ выдан.")
        await _clear_callback_keyboard(callback)
        if callback.message:
            await callback.message.answer(f"Пользователь {user_id} добавлен в whitelist.")
        await _safe_send(
            bot=callback.bot,
            chat_id=user_id,
            text="Администратор выдал вам доступ к боту. Можно отправлять ссылку.",
        )

    @router.callback_query(F.data.startswith("reject_user:"))
    async def reject_user_callback(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id, settings):
            await callback.answer("Только администратор может отклонять заявки.", show_alert=True)
            return
        user_id = _parse_callback_user_id(callback.data)
        if user_id is None:
            await callback.answer("Некорректная заявка.", show_alert=True)
            return
        await callback.answer("Заявка отклонена.")
        await _clear_callback_keyboard(callback)
        if callback.message:
            await callback.message.answer(f"Заявка пользователя {user_id} отклонена.")

    @router.callback_query(F.data.startswith("cancel_download:"))
    async def cancel_download_callback(callback: CallbackQuery) -> None:
        task = await _task_from_callback(
            callback,
            store,
            expected_status=WAITING_DOWNLOAD_CONFIRMATION,
        )
        if task is None:
            return
        await callback.answer()
        await _clear_callback_keyboard(callback)
        await _remove_task(task, store, settings, CANCELLED)
        if callback.message:
            await callback.message.answer("Отменено.")

    @router.callback_query(F.data.startswith("confirm_download:"))
    async def confirm_download_callback(callback: CallbackQuery, bot: Bot) -> None:
        task = await _task_from_callback(
            callback,
            store,
            expected_status=WAITING_DOWNLOAD_CONFIRMATION,
        )
        if task is None:
            return
        await callback.answer()
        await _clear_callback_keyboard(callback)
        if callback.message:
            await callback.message.answer("Начинаю скачивание...")

        await store.set_status(task.task_id, DOWNLOADING)
        started_domain = task.context.get("domain") or url_domain(task.url)

        try:
            downloaded_path = await _download_with_quality_fallback(task, settings)
            await store.update(task.task_id, downloaded_file_path=downloaded_path)
            downloaded_size = file_size(downloaded_path)
            logger.info(
                "download_ok user_id=%s platform=%s content_type=%s domain=%s downloaded_size=%s status=%s",
                task.user_id,
                task.platform,
                task.content_type,
                started_domain,
                downloaded_size,
                DOWNLOADING,
            )

            if downloaded_size > settings.telegram_upload_limit_bytes:
                await _remove_task(task, store, settings, FAILED)
                if callback.message:
                    await callback.message.answer(TOO_LARGE_MESSAGE)
                return

            await _send_and_finish(bot, task, downloaded_path, store, settings)
        except InstagramAuthError:
            await _remove_task(task, store, settings, FAILED)
            await _notify_instagram_auth_problem(bot, settings)
            if callback.message:
                await callback.message.answer(INSTAGRAM_USER_AUTH_MESSAGE)
        except DownloadError:
            await _remove_task(task, store, settings, FAILED)
            if callback.message:
                await callback.message.answer(DOWNLOAD_FAILED_MESSAGE)
        except Exception:
            logger.exception("Unhandled download flow error task_id=%s user_id=%s", task.task_id, task.user_id)
            await _remove_task(task, store, settings, FAILED)
            if callback.message:
                await callback.message.answer(INTERNAL_ERROR_MESSAGE)

    return router


def _downloader_for_task(settings: Settings, task: PendingTask):
    if task.content_type == "instagram_story":
        return InstagramStoryDownloader(settings)
    return YtDlpDownloader(settings, task.platform, task.content_type)


async def _download_with_quality_fallback(task: PendingTask, settings: Settings) -> Path:
    if task.content_type == "instagram_story":
        return await InstagramStoryDownloader(settings).download(task.url, task.work_dir or settings.workdir)

    downloader = YtDlpDownloader(settings, task.platform, task.content_type)
    work_dir = task.work_dir or settings.workdir
    heights = [height for height in QUALITY_FALLBACKS if height <= settings.max_video_height]
    if settings.max_video_height not in heights:
        heights.insert(0, settings.max_video_height)

    last_path: Path | None = None
    for height in heights:
        _clear_work_dir_files(work_dir)
        path = await downloader.download(task.url, work_dir, max_height=height)
        last_path = path
        size = file_size(path)
        logger.info(
            "download_candidate task_id=%s user_id=%s max_height=%s size=%s limit=%s",
            task.task_id,
            task.user_id,
            height,
            size,
            settings.telegram_upload_limit_bytes,
        )
        if size <= settings.telegram_upload_limit_bytes:
            return path

    if last_path is None:
        raise DownloadError("No downloaded file")
    return last_path


async def _ensure_allowed_message(
    message: Message,
    bot: Bot,
    settings: Settings,
    access_store: AccessStore,
) -> bool:
    if message.from_user is None:
        return False
    user_id = message.from_user.id
    if is_admin(user_id, settings) or await access_store.is_allowed(user_id):
        return True
    await message.answer(access_denied_message(user_id))
    await _notify_admin_access_request(bot, settings, message)
    return False


async def _ensure_admin(message: Message, settings: Settings) -> bool:
    if message.from_user is None:
        return False
    if is_admin(message.from_user.id, settings):
        return True
    await message.answer("Эта команда доступна только администратору.")
    return False


async def _notify_admin_access_request(
    bot: Bot,
    settings: Settings,
    message: Message,
) -> None:
    if settings.admin_user_id is None or message.from_user is None:
        return
    user = message.from_user
    name_parts = [part for part in [user.full_name, f"@{user.username}" if user.username else None] if part]
    label = " ".join(name_parts) or "Без имени"
    text = (
        "Новая заявка на доступ к боту.\n\n"
        f"Пользователь: {label}\n"
        f"Telegram ID: {user.id}"
    )
    try:
        await bot.send_message(
            chat_id=settings.admin_user_id,
            text=text,
            reply_markup=access_request_keyboard(user.id),
        )
    except Exception:
        logger.exception("Failed to notify admin about access request user_id=%s", user.id)


def _extract_first_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,;!?)>]\"'")


def _parse_user_id_argument(text: str) -> int | None:
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    raw = parts[1].strip()
    return int(raw) if raw.isdigit() else None


def _parse_callback_user_id(data: str | None) -> int | None:
    if not data or ":" not in data:
        return None
    raw = data.split(":", 1)[1]
    return int(raw) if raw.isdigit() else None


async def _task_from_callback(
    callback: CallbackQuery,
    store: PendingTaskStore,
    *,
    expected_status: str,
) -> PendingTask | None:
    task_id = (callback.data or "").split(":", 1)[-1]
    task = await store.get(task_id)
    if task is None:
        await callback.answer("Задача устарела. Отправьте ссылку заново.", show_alert=True)
        if callback.message:
            await callback.message.answer("Задача устарела. Отправьте ссылку заново.")
        return None
    if callback.from_user.id != task.user_id:
        await callback.answer("Это не ваша задача.", show_alert=True)
        return None
    if task.status != expected_status:
        await callback.answer("Задача устарела. Отправьте ссылку заново.", show_alert=True)
        return None
    return task


async def _clear_callback_keyboard(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


async def _send_and_finish(
    bot: Bot,
    task: PendingTask,
    file_path: Path,
    store: PendingTaskStore,
    settings: Settings,
) -> None:
    await store.set_status(task.task_id, SENDING)
    await send_video_result(
        bot,
        chat_id=task.chat_id,
        file_path=file_path,
        metadata=task.metadata or _fallback_metadata(task),
        use_file_uri=settings.telegram_local_mode,
    )
    logger.info(
        "sent_video user_id=%s platform=%s content_type=%s file_size=%s status=%s local_api=%s",
        task.user_id,
        task.platform,
        task.content_type,
        format_size(file_size(file_path)),
        COMPLETED,
        settings.telegram_local_mode,
    )
    await _remove_task(task, store, settings, COMPLETED)


async def _remove_task(
    task: PendingTask,
    store: PendingTaskStore,
    settings: Settings,
    status: str,
) -> None:
    await store.set_status(task.task_id, status)
    await store.remove(task.task_id)
    try:
        remove_task_work_dir(task.work_dir, settings)
    except Exception:
        logger.exception("Failed to remove task workdir task_id=%s", task.task_id)


async def _notify_instagram_auth_problem(bot: Bot, settings: Settings) -> None:
    if settings.admin_user_id is None:
        return
    try:
        await bot.send_message(
            chat_id=settings.admin_user_id,
            text=INSTAGRAM_ADMIN_AUTH_MESSAGE,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception("Failed to notify admin about Instagram auth problem")


async def _safe_send(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.info("Failed to send service message to user_id=%s", chat_id, exc_info=True)


def _clear_work_dir_files(work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    for path in work_dir.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def _fallback_metadata(task: PendingTask) -> VideoMetadata:
    return VideoMetadata(title="Видео", platform=task.platform, content_type=task.content_type)
