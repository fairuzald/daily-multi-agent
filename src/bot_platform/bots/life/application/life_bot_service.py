from __future__ import annotations

from datetime import datetime

from bot_platform.bots.life.application.item_service import LifeItemService
from bot_platform.bots.life.application.message_service import LifeMessageService
from bot_platform.bots.life.application.rendering import LifeRenderingService
from bot_platform.bots.life.domain.responses import LifeBotResponse
from bot_platform.bots.life.domain.parser import LifeItemParser
from bot_platform.bots.life.infrastructure.calendar_gateway import GoogleCalendarGateway
from bot_platform.bots.life.infrastructure.repositories import LifeRepository
from bot_platform.bots.life.infrastructure.state_store import LifeReplyContext, LifeStateStore


class LifeBotService:
    def __init__(
        self,
        *,
        repository: LifeRepository,
        state_store: LifeStateStore,
        calendar_gateway: GoogleCalendarGateway,
        ai_client=None,
        default_timezone: str = "Asia/Jakarta",
    ) -> None:
        self.repository = repository
        self.state_store = state_store
        self.calendar_gateway = calendar_gateway
        self.ai_client = ai_client
        self.parser = LifeItemParser(default_timezone)
        self.default_timezone = default_timezone
        self.rendering = LifeRenderingService(default_timezone)
        self.item_service = LifeItemService(
            repository=repository,
            calendar_gateway=calendar_gateway,
            rendering=self.rendering,
            default_timezone=default_timezone,
        )
        self.message_service = LifeMessageService(
            state_store=state_store,
            ai_client=ai_client,
            parser=self.parser,
            item_service=self.item_service,
            default_timezone=default_timezone,
        )

    def handle_start(self, user_id: int, chat_id: int) -> LifeBotResponse:
        self._claim_or_require_owner(user_id, chat_id)
        return LifeBotResponse(
            "Life bot siap dipakai.\n\n"
            "Contoh pesan yang bisa langsung kamu kirim:\n"
            "- bayar wifi besok jam 9\n"
            "- ingatkan cek transfer 5 menit lagi\n"
            "- follow up Aldi Selasa depan jam 8 malam\n"
            "- ulang tahun ibu 12 Mei\n"
            "- bayar kos tiap bulan sampai 30 Mei 2026\n\n"
            "Kamu juga bisa balas item yang sudah kusimpan lalu kirim:\n"
            "- `done`\n"
            "- `hapus ini`\n"
            "- `detail ini`\n"
            "- `ubah jadi besok jam 1 siang`\n"
            "- `snooze 2hours`\n\n"
            "Perintah penting:\n"
            "- `/today`, `/tomorrow`, `/upcoming`, `/overdue`\n"
            "- `/followups`, `/dates`\n"
            "- `/done`, `/cancel`, `/delete`, `/view`, `/edit`, `/snooze`\n\n"
            "Kalau pesannya masih ambigu, aku bakal minta klarifikasi dulu daripada nebak."
        )

    def handle_help(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.handle_start(user_id, self.state_store.get_owner_chat_id() or 0)

    def handle_status(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        items = self.repository.list_all()
        open_items = [item for item in items if item.status.value in {"open", "snoozed"}]
        pending = self.state_store.get_pending_parse(self.state_store.get_owner_chat_id() or 0)
        return LifeBotResponse(
            f"Total items: {len(items)}\n"
            f"Open items: {len(open_items)}\n"
            f"Pending rewrite: {'yes' if pending else 'no'}\n"
            f"Calendar sync: {'on' if self.calendar_gateway.enabled() else 'off'}"
        )

    def handle_whoami(self, user_id: int, chat_id: int) -> LifeBotResponse:
        owner_user_id = self.state_store.get_owner_user_id()
        owner_chat_id = self.state_store.get_owner_chat_id()
        is_owner = owner_user_id == user_id
        return LifeBotResponse(
            f"Your Telegram user ID: {user_id}\n"
            f"Your Telegram chat ID: {chat_id}\n"
            f"Stored owner user ID: {owner_user_id or '-'}\n"
            f"Stored owner chat ID: {owner_chat_id or '-'}\n"
            f"Owner match: {'yes' if is_owner else 'no'}"
        )

    def handle_text_message(
        self,
        user_id: int,
        chat_id: int,
        text: str,
        *,
        message_datetime: datetime | None = None,
        reply_context: LifeReplyContext | None = None,
    ) -> LifeBotResponse:
        self._claim_or_require_owner(user_id, chat_id)
        return self.message_service.handle_text_message(
            chat_id,
            text,
            message_datetime=message_datetime,
            reply_context=reply_context,
        )

    def handle_voice_transcript(
        self,
        user_id: int,
        chat_id: int,
        transcript: str,
        *,
        message_datetime: datetime | None = None,
        reply_context: LifeReplyContext | None = None,
    ) -> LifeBotResponse:
        return self.handle_text_message(
            user_id,
            chat_id,
            transcript,
            message_datetime=message_datetime,
            reply_context=reply_context,
        )

    def handle_today(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_today()

    def handle_upcoming(self, user_id: int, days: int = 7) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_upcoming(days=days)

    def handle_overdue(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_overdue()

    def handle_followups(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_followups()

    def handle_important_dates(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_important_dates()

    def handle_done_latest(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_done_latest()

    def handle_done(self, user_id: int, item_id_fragment: str) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_done(item_id_fragment)

    def handle_snooze(self, user_id: int, item_id_fragment: str, amount: int, unit: str) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_snooze(item_id_fragment, amount, unit)

    def handle_snooze_latest(self, user_id: int, amount: int, unit: str) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_snooze_latest(amount, unit)

    def handle_cancel(self, user_id: int, item_id_fragment: str) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_cancel(item_id_fragment)

    def handle_cancel_latest(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_cancel_latest()

    def handle_delete(self, user_id: int, item_id_fragment: str) -> LifeBotResponse:
        return self.handle_cancel(user_id, item_id_fragment)

    def handle_delete_latest(self, user_id: int) -> LifeBotResponse:
        return self.handle_cancel_latest(user_id)

    def handle_view(self, user_id: int, item_id_fragment: str) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_view(item_id_fragment)

    def handle_view_latest(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.item_service.handle_view_latest()

    def handle_edit(
        self,
        user_id: int,
        item_id_fragment: str,
        correction_text: str,
        *,
        message_datetime: datetime | None = None,
    ) -> LifeBotResponse:
        self._ensure_owner(user_id)
        item = self.item_service.find_item(item_id_fragment)
        batch = self.message_service.extract_items(correction_text, original_input=item.raw_input or item.title, message_datetime=message_datetime)
        if batch.needs_manual_review or not batch.items:
            return LifeBotResponse("Aku masih belum yakin perubahan yang kamu mau. Coba tulis ulang lebih jelas, misalnya: `ubah jadi bayar wifi besok jam 1 siang`.")
        return self.item_service.update_item_from_parsed(
            item_id_fragment,
            batch.items[0],
            correction_text=correction_text,
            message_datetime=message_datetime,
        )

    def handle_edit_latest(
        self,
        user_id: int,
        correction_text: str,
        *,
        message_datetime: datetime | None = None,
    ) -> LifeBotResponse:
        self._ensure_owner(user_id)
        item = self.item_service.latest_active_item()
        if item is None:
            return LifeBotResponse("Aku belum menemukan item aktif yang bisa diubah.")
        return self.handle_edit(user_id, item.item_id, correction_text, message_datetime=message_datetime)

    def item_reply_context(self, item) -> LifeReplyContext:
        return self.item_service.item_reply_context(item)

    def pending_reply_context(self) -> LifeReplyContext:
        return self.message_service.pending_reply_context()

    async def dispatch_due_reminders(self, *, bot) -> int:
        return await self.item_service.dispatch_due_reminders_async(
            bot=bot,
            chat_id=self.state_store.get_owner_chat_id(),
        )

    def _claim_or_require_owner(self, user_id: int, chat_id: int) -> None:
        owner = self.state_store.get_owner_user_id()
        if owner is None:
            self.state_store.set_owner_user_id(user_id)
            self.state_store.set_owner_chat_id(chat_id)
            return
        if owner != user_id:
            raise PermissionError("This bot is locked to a different Telegram user. Send /whoami to compare your current Telegram user ID with the stored owner.")
        self.state_store.set_owner_chat_id(chat_id)

    def _ensure_owner(self, user_id: int) -> None:
        owner = self.state_store.get_owner_user_id()
        if owner is None:
            raise PermissionError("No owner is set yet. Send /start first from the owner account.")
        if owner != user_id:
            raise PermissionError("This bot is locked to a different Telegram user. Send /whoami to compare your current Telegram user ID with the stored owner.")
