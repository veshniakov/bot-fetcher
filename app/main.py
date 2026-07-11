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
from app.access_store import AccessStore
from app.router import create_router
from app.tasks import PendingTaskStore
from storage.cleanup import cleanup_old_work_files, cleanup_pending_tasks_loop
from storage.paths import ensure_data_dirs
from utils.logging import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

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
    access_store = AccessStore(settings)
    await access_store.load()
    dispatcher.include_router(create_router(settings, store, access_store))

    cleanup_task = asyncio.create_task(cleanup_pending_tasks_loop(settings, store))

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Начать работу"),
                BotCommand(command="help", description="Помощь"),
                BotCommand(command="id", description="Показать Telegram ID"),
                BotCommand(command="allow", description="Разрешить пользователя"),
                BotCommand(command="deny", description="Удалить пользователя"),
                BotCommand(command="users", description="Показать whitelist"),
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
