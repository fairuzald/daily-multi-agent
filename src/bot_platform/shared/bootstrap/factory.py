from __future__ import annotations

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot_platform.bots.finance.application.finance_bot_service import FinanceBotService
from bot_platform.bots.finance.infrastructure.ai_router import RotatingAIClient
from bot_platform.bots.finance.infrastructure.gemini_gateway import GeminiClient
from bot_platform.bots.finance.infrastructure.openrouter_gateway import OpenRouterClient
from bot_platform.bots.finance.infrastructure.repositories import FinanceRepository
from bot_platform.bots.finance.infrastructure.sheets_gateway import GoogleSheetsClient
from bot_platform.bots.finance.infrastructure.state_store import BotStateStore
from bot_platform.bots.finance.domain.summary_service import SummaryService
from bot_platform.bots.finance.interfaces.telegram.controller import TelegramBotController
from bot_platform.shared.config.settings import Settings


def build_finance_bot_service(settings: Settings) -> FinanceBotService:
    gemini_client = GeminiClient(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
    openrouter_client = None
    if settings.openrouter_api_key:
        openrouter_client = OpenRouterClient(
            api_key=settings.openrouter_api_key,
            text_models=settings.openrouter_models_text,
            vision_models=settings.openrouter_models_vision,
            audio_models=settings.openrouter_models_audio,
            base_url=settings.openrouter_base_url,
        )
    if settings.primary_ai_provider == "openrouter":
        primary_client = openrouter_client
        fallback_client = gemini_client
    else:
        primary_client = gemini_client
        fallback_client = openrouter_client
    if primary_client is None:
        raise RuntimeError(f"Primary AI provider `{settings.primary_ai_provider}` is not configured.")
    ai_client = RotatingAIClient(
        primary=primary_client,
        fallback=fallback_client,
        cooldown_seconds=settings.ai_fallback_cooldown_seconds,
    )
    return FinanceBotService(
        gemini_client=ai_client,
        sheets_client_factory=lambda sheet_id: GoogleSheetsClient(
            spreadsheet_id=sheet_id,
            service_account_json=settings.google_service_account_json,
        ),
        summary_service=SummaryService(),
        state_store=BotStateStore(settings.database_url),
        finance_repository=FinanceRepository(settings.database_url),
        low_confidence_threshold=settings.low_confidence_threshold,
        service_account_email=settings.service_account_email(),
        default_timezone=settings.default_timezone,
    )


def build_telegram_controller(settings: Settings) -> TelegramBotController:
    return TelegramBotController(build_finance_bot_service(settings))


def create_application_components(settings: Settings) -> tuple[FinanceBotService, TelegramBotController]:
    bot_service = build_finance_bot_service(settings)
    controller = TelegramBotController(bot_service)
    return bot_service, controller


def create_telegram_application(settings: Settings) -> Application:
    missing = settings.validate_required()
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    bot_service, controller = create_application_components(settings)
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["bot_handlers"] = bot_service
    app.bot_data["telegram_controller"] = controller
    app.add_handler(CommandHandler("start", controller.start_command))
    app.add_handler(CommandHandler("help", controller.help_command))
    app.add_handler(CommandHandler("status", controller.status_command))
    app.add_handler(CommandHandler("whoami", controller.whoami_command))
    app.add_handler(CommandHandler("set_sheet", controller.set_sheet_command))
    app.add_handler(CommandHandler("add_payment_method", controller.add_payment_method_command))
    app.add_handler(CommandHandler("add_categories", controller.add_categories_command))
    app.add_handler(CommandHandler("today", controller.today_command))
    app.add_handler(CommandHandler("week", controller.week_command))
    app.add_handler(CommandHandler("month", controller.month_command))
    app.add_handler(CommandHandler("moth", controller.month_command))
    app.add_handler(CommandHandler("delete_last", controller.delete_last_command))
    app.add_handler(CommandHandler("delete_reply", controller.delete_reply_command))
    app.add_handler(CommandHandler("edit_last", controller.edit_last_command))
    app.add_handler(CommandHandler("edit_reply", controller.edit_reply_command))
    app.add_handler(CommandHandler("read", controller.read_command))
    app.add_handler(CommandHandler("budget_set", controller.budget_set_command))
    app.add_handler(CommandHandler("budget_show", controller.budget_show_command))
    app.add_handler(CommandHandler("compare_month", controller.compare_month_command))
    app.add_handler(MessageHandler(filters.VOICE, controller.voice_message))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, controller.photo_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, controller.text_message))
    app.add_error_handler(controller.application_error_handler)
    return app
