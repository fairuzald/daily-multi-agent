from __future__ import annotations

from datetime import datetime

from bot_platform.bots.life.application.item_service import LifeItemService
from bot_platform.bots.life.domain.language import (
    CANCEL_TOKENS,
    CONFIRM_CANCEL_TOKENS,
    CONFIRM_SAVE_TOKENS,
    DONE_TOKENS,
    EDIT_PREFIXES,
    PENDING_REWRITE_CANCEL_TOKENS,
    SNOOZE_PREFIXES,
    VIEW_TOKENS,
)
from bot_platform.bots.life.domain.models import ParsedLifeBatch
from bot_platform.bots.life.domain.parser import LifeItemParser
from bot_platform.bots.life.domain.responses import LifeBotResponse
from bot_platform.bots.life.infrastructure.state_store import (
    LifeReplyContext,
    LifeStateStore,
    PendingLifeConfirmationState,
    PendingLifeParseState,
)


class LifeMessageService:
    def __init__(
        self,
        *,
        state_store: LifeStateStore,
        ai_client,
        parser: LifeItemParser,
        item_service: LifeItemService,
        default_timezone: str = "Asia/Jakarta",
    ) -> None:
        self.state_store = state_store
        self.ai_client = ai_client
        self.parser = parser
        self.item_service = item_service
        self.default_timezone = default_timezone

    def handle_text_message(
        self,
        chat_id: int,
        text: str,
        *,
        message_datetime: datetime | None = None,
        reply_context: LifeReplyContext | None = None,
    ) -> LifeBotResponse:
        if reply_context and reply_context.kind == "item":
            action_response = self._handle_inline_action(text, reply_item_id=reply_context.item_id, message_datetime=message_datetime)
            if action_response is not None:
                return action_response

        if reply_context and reply_context.kind == "pending":
            pending = self.state_store.get_pending_parse(chat_id)
            if pending is None:
                return LifeBotResponse("That pending rewrite expired. Please send the reminder again.")
            return self._handle_pending_rewrite(chat_id, pending, text, message_datetime=message_datetime)

        if reply_context and reply_context.kind == "confirmation":
            pending_confirmation = self.state_store.get_pending_confirmation(chat_id)
            if pending_confirmation is None:
                return LifeBotResponse("That confirmation expired. Please send the schedule again.")
            return self._handle_pending_confirmation(chat_id, pending_confirmation, text, message_datetime=message_datetime)

        action_response = self._handle_inline_action(text, message_datetime=message_datetime)
        if action_response is not None:
            return action_response

        batch = self.parse_items(text, message_datetime=message_datetime)
        if batch.needs_manual_review or not batch.items:
            return self._queue_manual_review(chat_id, text, batch)
        return self._save_or_confirm_batch(chat_id, batch, message_datetime=message_datetime)

    def parse_items(self, text: str, *, message_datetime: datetime | None) -> ParsedLifeBatch:
        if self.ai_client is None:
            return ParsedLifeBatch(items=[self.parser.parse(text, message_datetime=message_datetime)])
        return self.extract_items(text, message_datetime=message_datetime)

    def extract_items(
        self,
        text: str,
        *,
        original_input: str = "",
        message_datetime: datetime | None,
    ) -> ParsedLifeBatch:
        if self.ai_client is None:
            fallback_text = text if text.strip() else original_input
            return ParsedLifeBatch(items=[self.parser.parse(fallback_text, message_datetime=message_datetime)])
        reference_time = self.item_service.reference_time(message_datetime)
        return self.ai_client.extract_life_items(
            text,
            original_input=original_input,
            reference_time_iso=reference_time.isoformat(),
            timezone_name=self.default_timezone,
        )

    def pending_reply_context(self) -> LifeReplyContext:
        return LifeReplyContext(kind="pending")

    def _handle_pending_rewrite(
        self,
        chat_id: int,
        pending: PendingLifeParseState,
        rewrite_text: str,
        *,
        message_datetime: datetime | None,
    ) -> LifeBotResponse:
        normalized = " ".join(rewrite_text.strip().lower().split())
        if normalized in PENDING_REWRITE_CANCEL_TOKENS:
            self.state_store.clear_pending_parse(chat_id)
            return LifeBotResponse("Oke, revisi yang pending aku batalkan.")
        batch = self.extract_items(rewrite_text, original_input=pending.raw_input, message_datetime=message_datetime)
        if batch.needs_manual_review or not batch.items:
            return self._queue_manual_review(chat_id, pending.raw_input, batch, correction_text=rewrite_text)
        self.state_store.clear_pending_parse(chat_id)
        return self._save_or_confirm_batch(chat_id, batch, message_datetime=message_datetime)

    def _handle_pending_confirmation(
        self,
        chat_id: int,
        pending: PendingLifeConfirmationState,
        text: str,
        *,
        message_datetime: datetime | None = None,
    ) -> LifeBotResponse:
        normalized = " ".join(text.strip().lower().split())
        if normalized in CONFIRM_SAVE_TOKENS:
            self.state_store.clear_pending_confirmation(chat_id)
            return self.item_service.save_batch(pending.batch, message_datetime=message_datetime)
        if normalized in CONFIRM_CANCEL_TOKENS:
            self.state_store.clear_pending_confirmation(chat_id)
            return LifeBotResponse("Oke, jadwal yang tadi jadi tidak kusimpan.")
        return LifeBotResponse("Balas `ya` kalau tetap mau kusimpan, atau `batal` kalau mau dibatalkan.", reply_context=LifeReplyContext(kind="confirmation"))

    def _save_or_confirm_batch(
        self,
        chat_id: int,
        batch: ParsedLifeBatch,
        *,
        message_datetime: datetime | None = None,
    ) -> LifeBotResponse:
        if self.item_service.batch_needs_confirmation(batch, message_datetime=message_datetime):
            self.state_store.set_pending_confirmation(chat_id, PendingLifeConfirmationState(batch=batch))
            item_preview = self.item_service.create_item_from_parsed(batch.items[0], message_datetime=message_datetime)
            scheduled_at = item_preview.scheduled_at() or self.item_service.reference_time(message_datetime)
            return LifeBotResponse(
                "Jadwal ini jatuh ke waktu yang sudah lewat.\n"
                f"- {item_preview.title}\n"
                f"- Waktu: {self.item_service.rendering.format_when(scheduled_at, all_day=item_preview.all_day)}\n"
                "Balas `ya` kalau tetap mau kusimpan, atau `batal` kalau mau dibatalkan.",
                reply_context=LifeReplyContext(kind="confirmation"),
            )
        self.state_store.clear_pending_confirmation(chat_id)
        return self.item_service.save_batch(batch, message_datetime=message_datetime)

    def _queue_manual_review(
        self,
        chat_id: int,
        original_text: str,
        batch: ParsedLifeBatch,
        *,
        correction_text: str = "",
    ) -> LifeBotResponse:
        raw_input = correction_text or original_text
        self.state_store.set_pending_parse(chat_id, PendingLifeParseState(raw_input=raw_input))
        lines = [
            "Aku masih belum yakin dengan maksud pesannya.",
            "Balas pesan ini dengan versi yang lebih jelas, nanti aku coba lagi.",
            "",
            "Contoh yang gampang kupahami:",
            "- bayar wifi besok jam 9",
            "- follow up Aldi Selasa depan jam 8 malam",
            "- ulang tahun ibu 12 Mei",
        ]
        if batch.manual_guidance:
            lines.insert(1, batch.manual_guidance)
        return LifeBotResponse("\n".join(lines), reply_context=self.pending_reply_context())

    def _handle_inline_action(
        self,
        text: str,
        *,
        reply_item_id: str = "",
        message_datetime: datetime | None = None,
    ) -> LifeBotResponse | None:
        compact_text = " ".join(text.strip().split())
        normalized = compact_text.lower()
        latest_item = self.item_service.latest_active_item()
        latest_item_id = latest_item.item_id if latest_item else ""

        if normalized in DONE_TOKENS:
            target_item = reply_item_id or latest_item_id
            if not target_item:
                return LifeBotResponse("Aku belum menemukan item aktif yang bisa ditandai selesai.")
            return self.item_service.handle_done(target_item)

        if normalized in CANCEL_TOKENS:
            target_item = reply_item_id or latest_item_id
            if not target_item:
                return LifeBotResponse("Aku belum menemukan item aktif yang bisa dibatalkan.")
            return self.item_service.handle_cancel(target_item)

        if normalized in VIEW_TOKENS:
            target_item = reply_item_id or latest_item_id
            if not target_item:
                return LifeBotResponse("Aku belum menemukan item aktif yang bisa ditampilkan.")
            return self.item_service.handle_view(target_item)

        correction_text = self._extract_edit_text(compact_text)
        if correction_text:
            target_item = reply_item_id or latest_item_id
            if not target_item:
                return LifeBotResponse("Aku belum menemukan item aktif yang bisa diubah.")
            current_item = self.item_service.find_item(target_item)
            batch = self.extract_items(correction_text, original_input=current_item.raw_input or current_item.title, message_datetime=message_datetime)
            if batch.needs_manual_review or not batch.items:
                return LifeBotResponse("Aku masih belum yakin perubahan yang kamu mau. Coba tulis ulang lebih jelas, misalnya: `ubah jadi bayar wifi besok jam 1 siang`.")
            return self.item_service.update_item_from_parsed(
                target_item,
                batch.items[0],
                correction_text=correction_text,
                message_datetime=message_datetime,
            )

        if any(normalized.startswith(prefix) for prefix in SNOOZE_PREFIXES):
            amount_text = "".join(ch for ch in normalized if ch.isdigit())
            if not amount_text:
                return LifeBotResponse("Send `snooze 2hours` or `snooze 2days`, or reply to a saved item with that message.")
            unit = "days" if "day" in normalized else "hours"
            target_item = reply_item_id or latest_item_id
            if not target_item:
                return LifeBotResponse("Aku belum menemukan item aktif yang bisa di-snooze.")
            return self.item_service.handle_snooze(target_item, int(amount_text), unit)
        return None

    @staticmethod
    def _extract_edit_text(text: str) -> str:
        lowered = text.lower()
        for prefix in EDIT_PREFIXES:
            if lowered.startswith(prefix):
                return text[len(prefix):].strip()
        return ""
