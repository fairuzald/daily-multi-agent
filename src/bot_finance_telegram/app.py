from __future__ import annotations

import logging
import re

from telegram import PhotoSize, Update
from telegram.ext import ContextTypes

from bot_finance_telegram.handlers import BotHandlers, BotResponse, ReplyContextInput

logger = logging.getLogger(__name__)


def _humanize_processing_error(exc: Exception, *, source: str) -> BotResponse:
    error_text = str(exc)

    if "RESOURCE_EXHAUSTED" in error_text or "quota exceeded" in error_text.lower() or "429" in error_text:
        retry_match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", error_text, flags=re.IGNORECASE)
        retry_seconds = ""
        if retry_match:
            retry_seconds = str(int(float(retry_match.group(1))))
        if retry_seconds:
            return BotResponse(
                f"Gemini quota is temporarily exhausted. Please wait about {retry_seconds} seconds and try again."
            )
        return BotResponse(
            "Gemini quota is temporarily exhausted. Please wait a bit and try again."
        )

    if "deadline" in error_text.lower() or "timeout" in error_text.lower():
        return BotResponse(
            f"The {source} took too long to process. Please try again with a shorter {source} or simpler input."
        )

    if "permission" in error_text.lower() or "forbidden" in error_text.lower():
        return BotResponse(
            "The bot could not access the AI service for that request. Please check the API key or try again later."
        )

    return BotResponse(
        f"I couldn't process that {source} safely right now. Please try again or send a simpler version."
    )


def _reply_context_input(update: Update) -> ReplyContextInput:
    if not update.message or not update.message.reply_to_message:
        return ReplyContextInput()
    reply_to_message = update.message.reply_to_message
    from_user = reply_to_message.from_user
    return ReplyContextInput(
        message_id=reply_to_message.message_id,
        is_bot_reply=bool(from_user and from_user.is_bot),
    )


async def _send_bot_response(update: Update, response: BotResponse, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    sent_message = await update.message.reply_text(str(response))
    reply_context = getattr(response, "reply_context", None)
    if reply_context is not None:
        bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
        bot_handlers.state_store.set_reply_context(update.effective_chat.id, sent_message.message_id, reply_context)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    await _send_bot_response(update, bot_handlers.handle_start(update.effective_user.id), context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    await _send_bot_response(update, bot_handlers.handle_help(update.effective_user.id), context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    await _send_bot_response(update, bot_handlers.handle_status(update.effective_user.id), context)


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    await _send_bot_response(update, bot_handlers.handle_whoami(update.effective_user.id), context)


async def set_sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    await _send_bot_response(update, bot_handlers.handle_set_sheet(update.effective_user.id), context)


async def add_payment_method_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    await _send_bot_response(
        update,
        bot_handlers.handle_add_payment_method(update.effective_user.id, update.effective_chat.id),
        context,
    )


async def add_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    await _send_bot_response(
        update,
        bot_handlers.handle_add_categories(update.effective_user.id, update.effective_chat.id),
        context,
    )


async def month_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    month = context.args[0] if context.args else None
    try:
        message = bot_handlers.handle_month_command(update.effective_user.id, month)
    except ValueError as exc:
        message = BotResponse(str(exc))
    await _send_bot_response(update, message, context)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    day = context.args[0] if context.args else None
    try:
        message = bot_handlers.handle_today_command(update.effective_user.id, day)
    except ValueError as exc:
        message = BotResponse(str(exc))
    await _send_bot_response(update, message, context)


async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    week = context.args[0] if context.args else None
    try:
        message = bot_handlers.handle_week_command(update.effective_user.id, week)
    except ValueError as exc:
        message = BotResponse(str(exc))
    await _send_bot_response(update, message, context)


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    if not update.message or not update.message.text:
        return
    try:
        normalized_text = update.message.text.strip().lower()
        if normalized_text == "/add-payment-method":
            reply = bot_handlers.handle_add_payment_method(update.effective_user.id, update.effective_chat.id)
            await _send_bot_response(update, reply, context)
            return
        if normalized_text == "/add-categories":
            reply = bot_handlers.handle_add_categories(update.effective_user.id, update.effective_chat.id)
            await _send_bot_response(update, reply, context)
            return
        reply = bot_handlers.handle_text_message(
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            message_text=update.message.text,
            reply_context=_reply_context_input(update),
        )
    except Exception as exc:
        logger.exception("Failed to process text message")
        reply = _humanize_processing_error(exc, source="message")
    await _send_bot_response(update, reply, context)


async def voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    if not update.message or not update.message.voice:
        return
    try:
        telegram_file = await context.bot.get_file(update.message.voice.file_id)
        audio_bytes = bytes(await telegram_file.download_as_bytearray())
        mime_type = update.message.voice.mime_type or "audio/ogg"
        transcript = bot_handlers.gemini_client.transcribe_voice_note(audio_bytes=audio_bytes, mime_type=mime_type)
        reply = bot_handlers.handle_voice_transcript(
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            transcript=transcript,
            reply_context=_reply_context_input(update),
        )
    except Exception as exc:
        logger.exception("Failed to process voice message")
        reply = _humanize_processing_error(exc, source="voice note")
    await _send_bot_response(update, reply, context)


async def photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_handlers: BotHandlers = context.application.bot_data["bot_handlers"]
    if not update.message:
        return
    try:
        telegram_file = None
        mime_type = "image/jpeg"
        caption = update.message.caption or ""

        if update.message.photo:
            largest_photo: PhotoSize = update.message.photo[-1]
            telegram_file = await context.bot.get_file(largest_photo.file_id)
        elif update.message.document and (update.message.document.mime_type or "").startswith("image/"):
            telegram_file = await context.bot.get_file(update.message.document.file_id)
            mime_type = update.message.document.mime_type or mime_type
        else:
            return

        image_bytes = bytes(await telegram_file.download_as_bytearray())
        parsed = bot_handlers.gemini_client.parse_transaction_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            caption=caption,
        )
        reply = bot_handlers.handle_image_message(
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            parsed=parsed,
            reply_context=_reply_context_input(update),
        )
    except Exception as exc:
        logger.exception("Failed to process image message")
        reply = _humanize_processing_error(exc, source="image")
    await _send_bot_response(update, reply, context)


async def application_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram bot error", exc_info=context.error)
    message = getattr(update, "message", None)
    if message:
        await message.reply_text("Something went wrong while processing your request. Please try again.")
