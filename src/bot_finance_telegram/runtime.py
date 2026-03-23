from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot_finance_telegram.config import Settings
from bot_finance_telegram.handlers import BotHandlers, BotResponse
from bot_finance_telegram.services.gemini_client import GeminiClient
from bot_finance_telegram.services.sheets_client import GoogleSheetsClient
from bot_finance_telegram.services.state_store import BotStateStore
from bot_finance_telegram.services.summary_service import SummaryService

logger = logging.getLogger(__name__)


def build_bot_handlers(settings: Settings) -> BotHandlers:
    gemini_client = GeminiClient(api_key=settings.gemini_api_key)
    return BotHandlers(
        gemini_client=gemini_client,
        sheets_client_factory=lambda sheet_id: GoogleSheetsClient(
            spreadsheet_id=sheet_id,
            service_account_json=settings.google_service_account_json,
        ),
        summary_service=SummaryService(),
        state_store=BotStateStore(settings.database_url),
        low_confidence_threshold=settings.low_confidence_threshold,
        service_account_email=settings.service_account_email(),
    )


def create_telegram_application(
    settings: Settings,
    *,
    start_command,
    help_command,
    status_command,
    whoami_command,
    set_sheet_command,
    add_payment_method_command,
    add_categories_command,
    today_command,
    week_command,
    month_command,
    voice_message,
    photo_message,
    text_message,
    application_error_handler,
) -> Application:
    missing = settings.validate_required()
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["bot_handlers"] = build_bot_handlers(settings)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("whoami", whoami_command))
    app.add_handler(CommandHandler("set_sheet", set_sheet_command))
    app.add_handler(CommandHandler("add_payment_method", add_payment_method_command))
    app.add_handler(CommandHandler("add_categories", add_categories_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("week", week_command))
    app.add_handler(CommandHandler("month", month_command))
    app.add_handler(CommandHandler("moth", month_command))
    app.add_handler(MessageHandler(filters.VOICE, voice_message))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, photo_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    app.add_error_handler(application_error_handler)
    return app


def get_bot_handlers(application: Application) -> BotHandlers:
    return application.bot_data["bot_handlers"]


async def process_webhook_update(application: Application, payload: dict[str, Any]) -> None:
    await application.initialize()
    try:
        update = Update.de_json(payload, application.bot)
        await application.process_update(update)
    finally:
        await application.shutdown()
