from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, KeyboardButton

from app.config import Settings
from app.stats import StatsManager
from app.user_settings import UserSettingsManager
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
from downloader.instagram_post_downloader import InstagramPostDownloader
from downloader.instagram_story_downloader import InstagramStoryDownloader
from downloader.platform_detector import SUPPORTED_MESSAGE, detect_platform
from downloader.ytdlp_downloader import YtDlpDownloader
from storage.paths import create_task_work_dir, file_size, remove_task_work_dir
from telegram.keyboards import mode_settings_keyboard
from telegram.sender import (
    send_audio_result,
    send_media_group_result,
    send_photo_result,
    send_preview,
    send_video_result,
)
from utils.formatting import format_size, url_domain
from utils.progress import DownloadProgressReporter
from video.metadata import VideoMetadata
from video.probe import probe_video

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)

BROKEN_LINK_MESSAGE = "Не удалось распознать ссылку."
NO_METADATA_MESSAGE = (
    "Не удалось получить информацию о медиа. Возможно, ссылка приватная "
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
    "Для Instagram Stories нужна ссылка на конкретную Story, а не общий профиль/stories."
)


def create_router(
    settings: Settings,
    store: PendingTaskStore,
    download_semaphore: asyncio.Semaphore,
    stats: StatsManager,
    user_settings: UserSettingsManager,
) -> Router:
    router = Router()

    def is_admin(user_id: int) -> bool:
        return settings.admin_user_id is not None and user_id == settings.admin_user_id

    @router.message(Command("id"))
    async def id_command(message: Message) -> None:
        if message.from_user is None:
            return
        await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")

    @router.message(Command("start"))
    async def start_command(message: Message, bot: Bot) -> None:
        user_id = message.from_user.id if message.from_user else 0
        reply_markup = None
        if is_admin(user_id):
            reply_markup = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📊 Статистика")]],
                resize_keyboard=True,
            )

        await message.answer(
            "👋 <b>Привет!</b> Я помогу скачать видео или извлечь аудио.\n\n"
            "📥 <b>Поддерживаются:</b>\n"
            "• YouTube & YouTube Shorts\n"
            "• Instagram (Reels, посты, карусели, Stories)\n"
            "• TikTok (без водяного знака)\n"
            "• Twitter / X, Reddit, Pinterest, VK Видео\n\n"
            "Просто отправьте ссылку, и я подготовлю превью с выбором качества (1080p, 720p, 480p) "
            "или извлеку MP3.\n\n"
            "⚙️ /mode — переключить Быстрый режим (авто-скачивание)",
            reply_markup=reply_markup,
        )

    @router.message(Command("help"))
    async def help_command(message: Message, bot: Bot) -> None:
        await message.answer(
            "📖 <b>Как пользоваться ботом:</b>\n\n"
            "1. Отправьте ссылку на видео или клип.\n"
            "2. Выберите желаемый формат:\n"
            "   • <b>🎬 720p HD</b> — быстрый оптимальный стандарт\n"
            "   • <b>🌟 1080p FHD</b> — максимальное качество\n"
            "   • <b>📱 480p</b> — компактный размер\n"
            "   • <b>🎵 Аудио (MP3)</b> — только звук с обложкой и тегами\n\n"
            "⚡ <b>Быстрый режим (/mode):</b>\n"
            "Если включён быстрый режим, короткие ролики (Shorts/Reels/TikTok до 5 мин) "
            "скачиваются автоматически в 720p сразу после отправки ссылки.\n\n"
            "📸 <b>Карусели / Альбомы:</b>\n"
            "Посты Instagram с несколькими фото или видео бот собирает и присылает единым альбомом.\n\n"
            "🚀 <i>Загрузка файлов до 2000 МБ благодаря локальному Telegram Bot API Server!</i>"
        )

    @router.message(Command("mode"))
    async def mode_command(message: Message) -> None:
        if message.from_user is None:
            return
        user_id = message.from_user.id
        is_quick = await user_settings.is_quick_mode(user_id)
        status_str = "⚡ <b>Быстрый (Quick Mode)</b>" if is_quick else "📋 <b>Обычный (с превью)</b>"
        desc = (
            "Ролики до 5 минут скачиваются автоматически сразу после отправки ссылки."
            if is_quick
            else "Для каждой ссылки показывается превью с возможностью выбора качества и аудио."
        )
        await message.answer(
            f"Текущий режим скачивания: {status_str}\n\n{desc}",
            reply_markup=mode_settings_keyboard(is_quick),
        )

    @router.callback_query(F.data == "toggle_quick_mode")
    async def toggle_quick_mode_callback(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            return
        user_id = callback.from_user.id
        new_val = await user_settings.toggle_quick_mode(user_id)
        status_str = "⚡ <b>Быстрый (Quick Mode)</b>" if new_val else "📋 <b>Обычный (с превью)</b>"
        desc = (
            "Ролики до 5 минут скачиваются автоматически сразу после отправки ссылки."
            if new_val
            else "Для каждой ссылки показывается превью с возможностью выбора качества и аудио."
        )
        await callback.answer(f"Режим переключен: {'Быстрый' if new_val else 'Обычный'}")
        if callback.message:
            try:
                await callback.message.edit_text(
                    f"Текущий режим скачивания: {status_str}\n\n{desc}",
                    reply_markup=mode_settings_keyboard(new_val),
                )
            except TelegramBadRequest:
                pass

    @router.message(Command("stats"))
    async def stats_command(message: Message) -> None:
        if message.from_user is None or not is_admin(message.from_user.id):
            return
        await _show_stats(message, stats, store, settings)

    @router.message(F.text == "📊 Статистика")
    async def stats_text_handler(message: Message) -> None:
        if message.from_user is None or not is_admin(message.from_user.id):
            return
        await _show_stats(message, stats, store, settings)

    @router.message(F.text)
    async def link_message(message: Message, bot: Bot) -> None:
        if message.from_user is None:
            return

        user_id = message.from_user.id
        chat_id = message.chat.id
        await stats.add_user(user_id)

        url = _extract_first_url(message.text or "")
        if not url:
            if message.text == "📊 Статистика":
                return
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

        downloader = _downloader_for_task(settings, task)

        try:
            try:
                metadata = await downloader.get_metadata(url)
            except Exception as meta_exc:
                if task.platform == "Instagram" and task.content_type != "instagram_story":
                    logger.info("Retrying Instagram metadata with InstagramPostDownloader: %s", meta_exc)
                    post_dl = InstagramPostDownloader(settings)
                    metadata = await post_dl.get_metadata(url)
                    task.content_type = "instagram_post"
                    await store.update(task.task_id, content_type="instagram_post")
                else:
                    raise

            await store.update(task.task_id, metadata=metadata)
            logger.info(
                "metadata_ok user_id=%s platform=%s content_type=%s domain=%s duration=%s status=%s",
                user_id,
                detected.platform,
                detected.content_type,
                detected.domain,
                metadata.duration,
                WAITING_DOWNLOAD_CONFIRMATION,
            )

            # Проверяем Quick Mode
            is_quick = await user_settings.is_quick_mode(user_id)
            is_auto_downloadable = (
                (metadata.duration and metadata.duration <= 300)
                or (task.content_type == "instagram_post")
            )
            if is_quick and is_auto_downloadable:
                status_msg = await message.answer("⚡ <b>Быстрый режим:</b> начинаю скачивание...")
                await _execute_download_flow(
                    bot=bot,
                    task=task,
                    target="post" if task.content_type == "instagram_post" else "720",
                    status_message=status_msg,
                    store=store,
                    settings=settings,
                    stats=stats,
                    download_semaphore=download_semaphore,
                )
                return

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

    @router.callback_query(F.data.startswith("dl:") | F.data.startswith("confirm_download:"))
    async def download_callback(callback: CallbackQuery, bot: Bot) -> None:
        data = callback.data or ""
        # Разбор целевого формата: dl:<task_id>:<target> или confirm_download:<task_id>
        if data.startswith("dl:"):
            parts = data.split(":")
            task_id = parts[1] if len(parts) > 1 else ""
            target = parts[2] if len(parts) > 2 else "720"
        else:
            task_id = data.split(":", 1)[-1]
            target = "720"

        task = await _task_from_callback(
            callback,
            store,
            expected_status=WAITING_DOWNLOAD_CONFIRMATION,
            task_id_override=task_id,
        )
        if task is None:
            return

        await callback.answer()
        await _clear_callback_keyboard(callback)

        if target == "audio":
            format_label = "аудио (MP3)"
        elif target == "post":
            format_label = "публикации"
        else:
            format_label = f"видео ({target}p)"

        status_msg = None
        if callback.message:
            status_msg = await callback.message.answer(f"⏳ Готовлю скачивание {format_label}...")

        await _execute_download_flow(
            bot=bot,
            task=task,
            target=target,
            status_message=status_msg,
            store=store,
            settings=settings,
            stats=stats,
            download_semaphore=download_semaphore,
        )

    return router


async def _execute_download_flow(
    bot: Bot,
    task: PendingTask,
    target: str,
    status_message: Message | None,
    store: PendingTaskStore,
    settings: Settings,
    stats: StatsManager,
    download_semaphore: asyncio.Semaphore,
) -> None:
    reporter = DownloadProgressReporter(status_message) if status_message else None

    if download_semaphore.locked() and status_message:
        await _safe_edit_text(status_message, "⏳ <b>Очередь сервера занята. Ожидайте...</b>")

    async with download_semaphore:
        await store.set_status(task.task_id, DOWNLOADING)
        started_domain = task.context.get("domain") or url_domain(task.url)
        work_dir = task.work_dir or settings.workdir

        if reporter:
            await reporter.start()

        try:
            if target == "audio":
                downloader = YtDlpDownloader(settings, task.platform, task.content_type)
                audio_path = await downloader.download_audio(
                    task.url,
                    work_dir,
                    progress_hook=reporter.ytdlp_hook if reporter else None,
                )
                if reporter:
                    await reporter.stop()
                if status_message:
                    await _safe_edit_text(status_message, "📤 <b>Отправка аудио в Telegram...</b>")

                await store.set_status(task.task_id, SENDING)
                await send_audio_result(
                    bot,
                    chat_id=task.chat_id,
                    file_path=audio_path,
                    metadata=task.metadata or _fallback_metadata(task),
                    use_file_uri=settings.telegram_local_mode,
                )
                await stats.increment_downloads()
                if status_message:
                    await _safe_delete_message(status_message)
                await _remove_task(task, store, settings, COMPLETED)
                return

            # Скачивание медиа (видео / публикация / альбом)
            if task.content_type == "instagram_post":
                if status_message:
                    await _safe_edit_text(status_message, "⏳ <b>Скачиваю публикацию Instagram...</b>")
                post_dl = InstagramPostDownloader(settings)
                all_media = await post_dl.download(task.url, work_dir)
                if reporter:
                    await reporter.stop()
            else:
                target_height = int(target) if target.isdigit() else 720
                try:
                    downloaded_path = await _download_with_quality_fallback(
                        task,
                        settings,
                        target_height=target_height,
                        progress_hook=reporter.ytdlp_hook if reporter else None,
                    )
                    if reporter:
                        await reporter.stop()
                    await store.update(task.task_id, downloaded_file_path=downloaded_path)
                    await _log_downloaded_media_probe(task, downloaded_path)
                    all_media = YtDlpDownloader._find_all_downloaded_files(work_dir)
                    if not all_media and downloaded_path.exists():
                        all_media = [downloaded_path]
                except Exception as dl_exc:
                    if task.platform == "Instagram" and task.content_type != "instagram_story":
                        logger.warning("Yt-dlp failed on Instagram, falling back to InstagramPostDownloader: %s", dl_exc)
                        if status_message:
                            await _safe_edit_text(status_message, "⏳ <b>Скачиваю публикацию Instagram...</b>")
                        post_dl = InstagramPostDownloader(settings)
                        all_media = await post_dl.download(task.url, work_dir)
                        if reporter:
                            await reporter.stop()
                    else:
                        raise

            if not all_media:
                raise DownloadError("No downloaded files found")

            total_size = sum(file_size(p) for p in all_media)
            logger.info(
                "download_ok user_id=%s platform=%s domain=%s files_count=%s total_size=%s",
                task.user_id,
                task.platform,
                started_domain,
                len(all_media),
                total_size,
            )

            if total_size > settings.telegram_upload_limit_bytes:
                await _remove_task(task, store, settings, FAILED)
                if status_message:
                    await _safe_edit_text(status_message, TOO_LARGE_MESSAGE)
                return

            await store.set_status(task.task_id, SENDING)

            if len(all_media) > 1:
                if status_message:
                    await _safe_edit_text(status_message, "📤 <b>Отправка альбома в Telegram...</b>")
                await send_media_group_result(
                    bot,
                    chat_id=task.chat_id,
                    file_paths=all_media,
                    metadata=task.metadata or _fallback_metadata(task),
                    use_file_uri=settings.telegram_local_mode,
                )
            else:
                single_file = all_media[0]
                if single_file.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    if status_message:
                        await _safe_edit_text(status_message, "📤 <b>Отправка фото в Telegram...</b>")
                    await send_photo_result(
                        bot,
                        chat_id=task.chat_id,
                        file_path=single_file,
                        metadata=task.metadata or _fallback_metadata(task),
                        use_file_uri=settings.telegram_local_mode,
                    )
                else:
                    if status_message:
                        await _safe_edit_text(status_message, "📤 <b>Отправка видео в Telegram...</b>")
                    await send_video_result(
                        bot,
                        chat_id=task.chat_id,
                        file_path=single_file,
                        metadata=task.metadata or _fallback_metadata(task),
                        use_file_uri=settings.telegram_local_mode,
                    )

            await stats.increment_downloads()
            if status_message:
                await _safe_delete_message(status_message)
            await _remove_task(task, store, settings, COMPLETED)

        except InstagramAuthError:
            if reporter:
                await reporter.stop()
            await _remove_task(task, store, settings, FAILED)
            await _notify_instagram_auth_problem(bot, settings)
            if status_message:
                await _safe_edit_text(status_message, INSTAGRAM_USER_AUTH_MESSAGE)
        except DownloadError:
            if reporter:
                await reporter.stop()
            await _remove_task(task, store, settings, FAILED)
            if status_message:
                await _safe_edit_text(status_message, DOWNLOAD_FAILED_MESSAGE)
        except Exception:
            if reporter:
                await reporter.stop()
            logger.exception("Unhandled download flow error task_id=%s user_id=%s", task.task_id, task.user_id)
            await _remove_task(task, store, settings, FAILED)
            if status_message:
                await _safe_edit_text(status_message, INTERNAL_ERROR_MESSAGE)
        finally:
            if reporter:
                await reporter.stop()


async def _show_stats(message: Message, stats: StatsManager, store: PendingTaskStore, settings: Settings) -> None:
    users, downloads = stats.get_audience_stats()
    active_tasks = await store.get_active_tasks_count()
    free_bytes, _ = StatsManager.get_system_stats(settings.workdir)
    free_gb = free_bytes / (1024 ** 3)

    text = (
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Уникальных пользователей: <b>{users}</b>\n"
        f"📥 Всего скачано: <b>{downloads}</b>\n\n"
        "⚙️ <b>Система:</b>\n"
        f"🔄 В работе (качается): <b>{active_tasks}</b> из 10\n"
        f"💾 Диск: свободно <b>{free_gb:.1f} GB</b>"
    )
    await message.answer(text)


def _downloader_for_task(settings: Settings, task: PendingTask):
    if task.content_type == "instagram_story":
        return InstagramStoryDownloader(settings)
    if task.content_type == "instagram_post":
        return InstagramPostDownloader(settings)
    return YtDlpDownloader(settings, task.platform, task.content_type)


async def _download_with_quality_fallback(
    task: PendingTask,
    settings: Settings,
    target_height: int = 720,
    progress_hook: Any = None,
) -> Path:
    if task.content_type == "instagram_story":
        return await InstagramStoryDownloader(settings).download(task.url, task.work_dir or settings.workdir)

    downloader = YtDlpDownloader(settings, task.platform, task.content_type)
    work_dir = task.work_dir or settings.workdir

    possible_heights = [1080, 720, 480, 360]
    heights = [h for h in possible_heights if h <= target_height]
    if not heights:
        heights = [target_height]

    last_path: Path | None = None
    for height in heights:
        _clear_work_dir_files(work_dir)
        path = await downloader.download(
            task.url,
            work_dir,
            max_height=height,
            progress_hook=progress_hook,
        )
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


def _extract_first_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,;!?)>]\"'")


async def _task_from_callback(
    callback: CallbackQuery,
    store: PendingTaskStore,
    *,
    expected_status: str,
    task_id_override: str | None = None,
) -> PendingTask | None:
    task_id = task_id_override or (callback.data or "").split(":", 1)[-1]
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


async def _safe_edit_text(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except Exception:
        pass


async def _safe_delete_message(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


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


def _clear_work_dir_files(work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    for path in work_dir.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def _fallback_metadata(task: PendingTask) -> VideoMetadata:
    return VideoMetadata(title="Видео", platform=task.platform, content_type=task.content_type)


async def _log_downloaded_media_probe(task: PendingTask, downloaded_path: Path) -> None:
    try:
        probe = await probe_video(downloaded_path)
    except Exception:
        logger.info("probe_failed task_id=%s user_id=%s", task.task_id, task.user_id, exc_info=True)
        return

    logger.info(
        "download_probe task_id=%s user_id=%s video_codec=%s audio_codec=%s width=%s height=%s duration=%s",
        task.task_id,
        task.user_id,
        probe.video_codec,
        probe.audio_codec,
        probe.width,
        probe.height,
        probe.duration,
    )
