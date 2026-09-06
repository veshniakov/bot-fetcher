from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import load_settings
from app.router import create_router
from app.stats import StatsManager
from app.tasks import PendingTaskStore
from app.user_settings import UserSettingsManager
from storage.cleanup import cleanup_old_work_files, cleanup_pending_tasks_loop
from storage.paths import ensure_data_dirs
from utils.logging import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    if settings.proxy_url:
        import os
        os.environ["http_proxy"] = settings.proxy_url
        os.environ["https_proxy"] = settings.proxy_url
        os.environ["HTTP_PROXY"] = settings.proxy_url
        os.environ["HTTPS_PROXY"] = settings.proxy_url
        os.environ["no_proxy"] = "telegram-bot-api,localhost,127.0.0.1,172.16.0.0/12,192.168.0.0/16"
        os.environ["NO_PROXY"] = "telegram-bot-api,localhost,127.0.0.1,172.16.0.0/12,192.168.0.0/16"
        logger.info("Configured outbound proxy: %s", settings.proxy_url)

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required")

    ensure_data_dirs(settings)
    cleanup_old_work_files(settings)

    session = None
    if settings.telegram_api_base_url:
        api_server = TelegramAPIServer.from_base(
            settings.telegram_api_base_url,
            is_local=settings.telegram_local_mode,
        )
        session = AiohttpSession(
            api=api_server,
            timeout=settings.telegram_request_timeout_seconds,
        )
        logger.info(
            "Using custom Telegram Bot API server: %s local=%s",
            settings.telegram_api_base_url,
            settings.telegram_local_mode,
        )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dispatcher = Dispatcher()
    store = PendingTaskStore()
    download_semaphore = asyncio.Semaphore(10)
    stats_manager = StatsManager(settings.workdir.parent / "stats.json")
    user_settings = UserSettingsManager(settings.workdir.parent / "user_settings.json")

    dispatcher.include_router(
        create_router(
            settings,
            store,
            download_semaphore,
            stats_manager,
            user_settings,
        )
    )

    cleanup_task = asyncio.create_task(cleanup_pending_tasks_loop(settings, store))

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Начать работу"),
                BotCommand(command="help", description="Помощь"),
                BotCommand(command="mode", description="Режим скачивания (Обычный/Быстрый)"),
                BotCommand(command="id", description="Показать Telegram ID"),
                BotCommand(command="stats", description="Статистика (только админ)"),
            ]
        )
        logger.info("Bot started in long polling mode")
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
