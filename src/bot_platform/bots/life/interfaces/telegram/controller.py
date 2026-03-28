from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot_platform.bots.life.application.life_bot_service import LifeBotService
from bot_platform.bots.life.domain.responses import LifeBotResponse
from bot_platform.bots.life.infrastructure.state_store import LifeReplyContext
from bot_platform.shared.telegram.errors import humanize_processing_error_text

logger = logging.getLogger(__name__)


class LifeTelegramController:
    def __init__(self, bot_service: LifeBotService) -> None:
        self.bot_service = bot_service

    def _reply_context(self, update: Update) -> LifeReplyContext | None:
        if not update.message or not update.message.reply_to_message:
            return None
        reply_to = update.message.reply_to_message
        from_user = reply_to.from_user
        if not from_user or not from_user.is_bot:
            return None
        return self.bot_service.state_store.get_reply_context(update.effective_chat.id, reply_to.message_id)

    async def _reply(self, update: Update, response: str | LifeBotResponse) -> None:
        if not update.message:
            return
        sent = await update.message.reply_text(str(response))
        reply_context = getattr(response, "reply_context", None)
        if reply_context is not None:
            self.bot_service.state_store.set_reply_context(update.effective_chat.id, sent.message_id, reply_context)

    def _log_processing_failure(self, exc: Exception, *, source: str) -> None:
        if isinstance(exc, PermissionError):
            logger.warning("Life bot %s rejected: %s", source, exc)
            return
        logger.exception("Failed to process life bot %s", source)

    async def _run_and_reply(self, update: Update, *, source: str, callback) -> None:
        try:
            response = callback()
        except Exception as exc:
            self._log_processing_failure(exc, source=source)
            response = LifeBotResponse(humanize_processing_error_text(exc, source=source))
        await self._reply(update, response)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_start(update.effective_user.id, update.effective_chat.id),
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_help(update.effective_user.id),
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_status(update.effective_user.id),
        )

    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_today(update.effective_user.id),
        )

    async def tomorrow_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_upcoming(update.effective_user.id, days=1),
        )

    async def upcoming_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        days = int(context.args[0]) if context.args and context.args[0].isdigit() else 7
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_upcoming(update.effective_user.id, days=days),
        )

    async def overdue_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_overdue(update.effective_user.id),
        )

    async def followups_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_followups(update.effective_user.id),
        )

    async def dates_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_important_dates(update.effective_user.id),
        )

    async def done_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        reply_context = self._reply_context(update)
        if reply_context is not None:
            await self._run_and_reply(
                update,
                source="command",
                callback=lambda: self.bot_service.handle_done(update.effective_user.id, reply_context.item_id),
            )
            return
        if len(context.args) == 0:
            await self._run_and_reply(
                update,
                source="command",
                callback=lambda: self.bot_service.handle_done_latest(update.effective_user.id),
            )
            return
        if len(context.args) != 1:
            await self._reply(update, "Use /done to mark the latest active item, or reply to a saved item and send /done.")
            return
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_done(update.effective_user.id, context.args[0]),
        )

    async def snooze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        reply_context = self._reply_context(update)
        if len(context.args) != 2:
            if len(context.args) == 1:
                amount_text = "".join(ch for ch in context.args[0] if ch.isdigit())
                unit = "days" if "day" in context.args[0].lower() else "hours"
                if amount_text:
                    if reply_context is not None:
                        await self._run_and_reply(
                            update,
                            source="command",
                            callback=lambda: self.bot_service.handle_snooze(update.effective_user.id, reply_context.item_id, int(amount_text), unit),
                        )
                        return
                    await self._run_and_reply(
                        update,
                        source="command",
                        callback=lambda: self.bot_service.handle_snooze_latest(update.effective_user.id, int(amount_text), unit),
                    )
                    return
            await self._reply(update, "Use /snooze 2hours for the latest active item, or reply to a saved item with /snooze 2hours.")
            return
        amount_text = "".join(ch for ch in context.args[1] if ch.isdigit())
        unit = "days" if "day" in context.args[1].lower() else "hours"
        if not amount_text:
            await self._reply(update, "Use /snooze 2hours for the latest active item, or reply to a saved item with /snooze 2hours.")
            return
        target = reply_context.item_id if reply_context is not None else context.args[0]
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_snooze(update.effective_user.id, target, int(amount_text), unit),
        )

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        reply_context = self._reply_context(update)
        if reply_context is not None:
            await self._run_and_reply(
                update,
                source="command",
                callback=lambda: self.bot_service.handle_cancel(update.effective_user.id, reply_context.item_id),
            )
            return
        if len(context.args) == 0:
            await self._run_and_reply(
                update,
                source="command",
                callback=lambda: self.bot_service.handle_cancel_latest(update.effective_user.id),
            )
            return
        if len(context.args) != 1:
            await self._reply(update, "Use /cancel for the latest active item, or reply to a saved item and send /cancel.")
            return
        await self._run_and_reply(
            update,
            source="command",
            callback=lambda: self.bot_service.handle_cancel(update.effective_user.id, context.args[0]),
        )

    async def delete_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.cancel_command(update, context)

    async def text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return
        try:
            reply_context = self._reply_context(update)
            response = self.bot_service.handle_text_message(
                update.effective_user.id,
                update.effective_chat.id,
                update.message.text,
                message_datetime=update.message.date,
                reply_context=reply_context,
            )
        except Exception as exc:
            self._log_processing_failure(exc, source="text message")
            response = LifeBotResponse(humanize_processing_error_text(exc, source="message"))
        await self._reply(update, response)

    async def voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.voice:
            return
        try:
            if self.bot_service.ai_client is None:
                raise RuntimeError("Voice note support is not configured for the life bot.")
            telegram_file = await context.bot.get_file(update.message.voice.file_id)
            audio_bytes = bytes(await telegram_file.download_as_bytearray())
            mime_type = update.message.voice.mime_type or "audio/ogg"
            transcript = self.bot_service.ai_client.transcribe_voice_note(audio_bytes=audio_bytes, mime_type=mime_type)
            reply_context = self._reply_context(update)
            response = self.bot_service.handle_voice_transcript(
                update.effective_user.id,
                update.effective_chat.id,
                transcript,
                message_datetime=update.message.date,
                reply_context=reply_context,
            )
        except Exception as exc:
            self._log_processing_failure(exc, source="voice message")
            response = LifeBotResponse(humanize_processing_error_text(exc, source="voice note"))
        await self._reply(update, response)

    async def application_error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled life bot error", exc_info=context.error)
        message = getattr(update, "message", None)
        if message:
            await message.reply_text("Something went wrong while processing your request. Please try again.")
