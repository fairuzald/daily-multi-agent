from __future__ import annotations

import logging

from telegram import PhotoSize, Update
from telegram.error import TimedOut
from telegram.ext import ContextTypes

from bot_platform.bots.finance.application.finance_bot_service import FinanceBotService
from bot_platform.bots.finance.domain.responses import BotResponse, ReplyContextInput
from bot_platform.shared.telegram.errors import humanize_processing_error_text

logger = logging.getLogger(__name__)


def humanize_processing_error(exc: Exception, *, source: str) -> BotResponse:
    return BotResponse(humanize_processing_error_text(exc, source=source))


class TelegramBotController:
    def __init__(self, bot_service: FinanceBotService) -> None:
        self.bot_service = bot_service

    @staticmethod
    def reply_context_input(update: Update) -> ReplyContextInput:
        if not update.message or not update.message.reply_to_message:
            return ReplyContextInput()
        reply_to_message = update.message.reply_to_message
        from_user = reply_to_message.from_user
        return ReplyContextInput(
            message_id=reply_to_message.message_id,
            is_bot_reply=bool(from_user and from_user.is_bot),
        )

    async def send_bot_response(
        self,
        update: Update,
        response: BotResponse,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not update.message:
            return
        try:
            sent_message = await update.message.reply_text(str(response))
        except TimedOut:
            logger.warning("Timed out sending Telegram response, retrying once")
            sent_message = await update.message.reply_text(str(response))
        reply_context = getattr(response, "reply_context", None)
        if reply_context is not None:
            self.bot_service.state_store.set_reply_context(update.effective_chat.id, sent_message.message_id, reply_context)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_bot_response(update, self.bot_service.handle_start(update.effective_user.id), context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_bot_response(update, self.bot_service.handle_help(update.effective_user.id), context)

    async def full_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_bot_response(update, self.bot_service.handle_full_help(update.effective_user.id), context)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_bot_response(update, self.bot_service.handle_status(update.effective_user.id), context)

    async def whoami_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_bot_response(update, self.bot_service.handle_whoami(update.effective_user.id), context)

    async def set_sheet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_bot_response(update, self.bot_service.handle_set_sheet(update.effective_user.id), context)

    async def add_payment_method_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_bot_response(
            update,
            self.bot_service.handle_add_payment_method(update.effective_user.id, update.effective_chat.id),
            context,
        )

    async def add_categories_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_bot_response(
            update,
            self.bot_service.handle_add_categories(update.effective_user.id, update.effective_chat.id),
            context,
        )

    async def month_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        month = context.args[0] if context.args else None
        try:
            message = self.bot_service.handle_month_command(update.effective_user.id, month)
        except ValueError as exc:
            message = BotResponse(str(exc))
        await self.send_bot_response(update, message, context)

    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        day = context.args[0] if context.args else None
        try:
            message = self.bot_service.handle_today_command(update.effective_user.id, day)
        except ValueError as exc:
            message = BotResponse(str(exc))
        await self.send_bot_response(update, message, context)

    async def week_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        week = context.args[0] if context.args else None
        try:
            message = self.bot_service.handle_week_command(update.effective_user.id, week)
        except ValueError as exc:
            message = BotResponse(str(exc))
        await self.send_bot_response(update, message, context)

    async def delete_last_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_bot_response(
            update,
            self.bot_service.handle_delete_last_command(update.effective_user.id, update.effective_chat.id),
            context,
        )

    async def delete_reply_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        reply_context = self.reply_context_input(update)
        if not reply_context.is_bot_reply:
            await self.send_bot_response(
                update,
                BotResponse("Usage: reply to a saved bot message, then send /delete_reply"),
                context,
            )
            return
        await self.send_bot_response(
            update,
            self.bot_service.handle_delete_reply_command(
                update.effective_user.id,
                update.effective_chat.id,
                reply_context,
            ),
            context,
        )

    async def edit_last_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await self.send_bot_response(
                update,
                BotResponse("Usage: /edit_last <amount> [payment_method]"),
                context,
            )
            return
        correction_input = self._strict_edit_correction_input(context.args)
        await self.send_bot_response(
            update,
            self.bot_service.handle_edit_last_command(
                update.effective_user.id,
                update.effective_chat.id,
                correction_input,
                message_datetime=update.message.date if update.message else None,
            ),
            context,
        )

    async def edit_reply_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await self.send_bot_response(
                update,
                BotResponse("Usage: reply to a saved bot message, then send /edit_reply <amount> [payment_method]"),
                context,
            )
            return
        reply_context = self.reply_context_input(update)
        if not reply_context.is_bot_reply:
            await self.send_bot_response(
                update,
                BotResponse("Usage: reply to a saved bot message, then send /edit_reply <amount> [payment_method]"),
                context,
            )
            return
        correction_input = self._strict_edit_correction_input(context.args)
        await self.send_bot_response(
            update,
            self.bot_service.handle_edit_reply_command(
                update.effective_user.id,
                update.effective_chat.id,
                correction_input,
                reply_context,
                message_datetime=update.message.date if update.message else None,
            ),
            context,
        )

    async def read_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args) != 2:
            await self.send_bot_response(
                update,
                BotResponse("Usage: /read <category> <today|week|month>"),
                context,
            )
            return
        category, period = context.args
        period = period.lower()
        if period not in {"today", "week", "month"}:
            await self.send_bot_response(
                update,
                BotResponse("Usage: /read <category> <today|week|month>"),
                context,
            )
            return
        await self.send_bot_response(
            update,
            self.bot_service.handle_read_strict_command(
                update.effective_user.id,
                category,
                period,
                message_datetime=update.message.date if update.message else None,
            ),
            context,
        )

    async def budget_set_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args) not in {3, 4}:
            await self.send_bot_response(
                update,
                BotResponse("Usage: /budget_set <weekly|monthly> <global|category> <amount> [category]"),
                context,
            )
            return
        period, scope, amount_text, *rest = context.args
        period = period.lower()
        scope = scope.lower()
        if period not in {"weekly", "monthly"} or scope not in {"global", "category"}:
            await self.send_bot_response(
                update,
                BotResponse("Usage: /budget_set <weekly|monthly> <global|category> <amount> [category]"),
                context,
            )
            return
        amount_digits = "".join(ch for ch in amount_text if ch.isdigit())
        if not amount_digits:
            await self.send_bot_response(
                update,
                BotResponse("Usage: /budget_set <weekly|monthly> <global|category> <amount> [category]"),
                context,
            )
            return
        category = " ".join(rest).strip()
        if scope == "category" and not category:
            await self.send_bot_response(
                update,
                BotResponse("Usage: /budget_set <weekly|monthly> <global|category> <amount> [category]"),
                context,
            )
            return
        await self.send_bot_response(
            update,
            self.bot_service.handle_budget_set_command(
                update.effective_user.id,
                period,
                scope,
                int(amount_digits),
                category,
            ),
            context,
        )

    async def budget_show_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args) != 1 or context.args[0].lower() not in {"weekly", "monthly"}:
            await self.send_bot_response(
                update,
                BotResponse("Usage: /budget_show <weekly|monthly>"),
                context,
            )
            return
        await self.send_bot_response(
            update,
            self.bot_service.handle_budget_show_command(
                update.effective_user.id,
                context.args[0].lower(),
                message_datetime=update.message.date if update.message else None,
            ),
            context,
        )

    async def compare_month_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if context.args:
            await self.send_bot_response(update, BotResponse("Usage: /compare_month"), context)
            return
        await self.send_bot_response(
            update,
            self.bot_service.handle_compare_month_command(
                update.effective_user.id,
                message_datetime=update.message.date if update.message else None,
            ),
            context,
        )

    async def text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return
        try:
            normalized_text = update.message.text.strip().lower()
            if normalized_text == "/add-payment-method":
                reply = self.bot_service.handle_add_payment_method(update.effective_user.id, update.effective_chat.id)
                await self.send_bot_response(update, reply, context)
                return
            if normalized_text == "/add-categories":
                reply = self.bot_service.handle_add_categories(update.effective_user.id, update.effective_chat.id)
                await self.send_bot_response(update, reply, context)
                return
            reply = self.bot_service.handle_text_message(
                user_id=update.effective_user.id,
                chat_id=update.effective_chat.id,
                message_text=update.message.text,
                reply_context=self.reply_context_input(update),
                message_datetime=update.message.date,
            )
        except Exception as exc:
            logger.exception("Failed to process text message")
            reply = humanize_processing_error(exc, source="message")
        await self.send_bot_response(update, reply, context)

    async def voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.voice:
            return
        try:
            telegram_file = await context.bot.get_file(update.message.voice.file_id)
            audio_bytes = bytes(await telegram_file.download_as_bytearray())
            mime_type = update.message.voice.mime_type or "audio/ogg"
            transcript = self.bot_service.ai_client.transcribe_voice_note(audio_bytes=audio_bytes, mime_type=mime_type)
            reply = self.bot_service.handle_voice_transcript(
                user_id=update.effective_user.id,
                chat_id=update.effective_chat.id,
                transcript=transcript,
                reply_context=self.reply_context_input(update),
                message_datetime=update.message.date,
            )
        except Exception as exc:
            logger.exception("Failed to process voice message")
            reply = humanize_processing_error(exc, source="voice note")
        await self.send_bot_response(update, reply, context)

    async def photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            parsed = self.bot_service.ai_client.parse_transaction_image(
                image_bytes=image_bytes,
                mime_type=mime_type,
                caption=caption,
            )
            reply = self.bot_service.handle_image_message(
                user_id=update.effective_user.id,
                chat_id=update.effective_chat.id,
                parsed=parsed,
                reply_context=self.reply_context_input(update),
                message_datetime=update.message.date,
            )
        except Exception as exc:
            logger.exception("Failed to process image message")
            reply = humanize_processing_error(exc, source="image")
        await self.send_bot_response(update, reply, context)

    async def application_error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled Telegram bot error", exc_info=context.error)
        message = getattr(update, "message", None)
        if message:
            await message.reply_text("Something went wrong while processing your request. Please try again.")

    @staticmethod
    def _strict_edit_correction_input(args: list[str]) -> str:
        amount = args[0]
        payment_method = " ".join(args[1:]).strip()
        if payment_method:
            return f"{amount} pakai {payment_method}"
        return amount
