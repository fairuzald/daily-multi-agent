from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot_platform.bots.life.application.rendering import LifeRenderingService
from bot_platform.bots.life.domain.models import LifeItem, LifeItemStatus, LifeItemType, ParsedLifeBatch, ParsedLifeItem
from bot_platform.bots.life.domain.responses import LifeBotResponse
from bot_platform.bots.life.domain.scheduling import advance_recurrence, shift_with_same_offset
from bot_platform.bots.life.infrastructure.calendar_gateway import GoogleCalendarGateway
from bot_platform.bots.life.infrastructure.repositories import LifeRepository
from bot_platform.bots.life.infrastructure.state_store import LifeReplyContext


class LifeItemService:
    def __init__(
        self,
        *,
        repository: LifeRepository,
        calendar_gateway: GoogleCalendarGateway,
        rendering: LifeRenderingService,
        default_timezone: str = "Asia/Jakarta",
    ) -> None:
        self.repository = repository
        self.calendar_gateway = calendar_gateway
        self.rendering = rendering
        self.default_timezone = default_timezone

    def handle_today(self) -> LifeBotResponse:
        today = self._now().date()
        items = [
            item
            for item in self.active_items()
            if item.scheduled_at() is not None and item.scheduled_at().astimezone(self._zone()).date() == today
        ]
        return self.rendering.render_items("Today", items)

    def handle_upcoming(self, days: int = 7) -> LifeBotResponse:
        now = self._now()
        cutoff = now + timedelta(days=days)
        items = [
            item
            for item in self.active_items()
            if item.scheduled_at() is not None and now <= item.scheduled_at().astimezone(self._zone()) <= cutoff
        ]
        return self.rendering.render_items(f"Upcoming {days} days", items)

    def handle_overdue(self) -> LifeBotResponse:
        now = self._now()
        items = [
            item
            for item in self.active_items()
            if item.scheduled_at() is not None and item.scheduled_at().astimezone(self._zone()) < now
        ]
        return self.rendering.render_items("Overdue", items)

    def handle_followups(self) -> LifeBotResponse:
        items = [item for item in self.active_items() if item.type == LifeItemType.FOLLOW_UP]
        return self.rendering.render_items("Follow-ups", items)

    def handle_important_dates(self) -> LifeBotResponse:
        items = [item for item in self.active_items() if item.type == LifeItemType.IMPORTANT_DATE]
        return self.rendering.render_items("Important dates", items)

    def handle_done(self, item_id_fragment: str) -> LifeBotResponse:
        item = self.find_item(item_id_fragment)
        now = self._now()
        if item.recurrence:
            next_due = advance_recurrence(item.due_at, item.recurrence, until_date=item.recurrence_until)
            if next_due is None:
                item = item.model_copy(update={"status": LifeItemStatus.DONE, "updated_at": now})
            else:
                item = item.model_copy(
                    update={
                        "due_at": next_due,
                        "remind_at": shift_with_same_offset(old_due_at=item.due_at, old_remind_at=item.remind_at, new_due_at=next_due),
                        "last_reminded_at": None,
                        "status": LifeItemStatus.OPEN,
                        "updated_at": now,
                    }
                )
        else:
            item = item.model_copy(update={"status": LifeItemStatus.DONE, "updated_at": now})
        if item.status == LifeItemStatus.DONE and item.calendar_event_id:
            self.calendar_gateway.delete_event(item.calendar_event_id)
            item = item.model_copy(update={"calendar_event_id": "", "calendar_event_url": ""})
        else:
            item, warning = self.sync_calendar(item)
            if warning:
                self.repository.save(item)
                return LifeBotResponse(f"Status item sekarang: {item.status.value}.\n{warning}")
        self.repository.save(item)
        return LifeBotResponse(f"Status item sekarang: {item.status.value}.")

    def handle_done_latest(self) -> LifeBotResponse:
        item = self.latest_active_item()
        if item is None:
            return LifeBotResponse("Aku belum menemukan item aktif yang bisa ditandai selesai.")
        return self.handle_done(item.item_id)

    def handle_snooze(self, item_id_fragment: str, amount: int, unit: str) -> LifeBotResponse:
        item = self.find_item(item_id_fragment)
        delta = timedelta(days=amount) if unit == "days" else timedelta(hours=amount)
        reminder_target = self._now() + delta
        item = item.model_copy(
            update={
                "status": LifeItemStatus.SNOOZED,
                "remind_at": reminder_target,
                "updated_at": self._now(),
            }
        )
        item, warning = self.sync_calendar(item)
        self.repository.save(item)
        message = f"Oke, aku snooze sampai {self.rendering.format_when(reminder_target, all_day=False)}."
        if warning:
            message = f"{message}\n{warning}"
        return LifeBotResponse(message)

    def handle_snooze_latest(self, amount: int, unit: str) -> LifeBotResponse:
        item = self.latest_active_item()
        if item is None:
            return LifeBotResponse("Aku belum menemukan item aktif yang bisa di-snooze.")
        return self.handle_snooze(item.item_id, amount, unit)

    def handle_cancel(self, item_id_fragment: str) -> LifeBotResponse:
        item = self.find_item(item_id_fragment)
        item = item.model_copy(update={"status": LifeItemStatus.CANCELLED, "updated_at": self._now()})
        if item.calendar_event_id:
            self.calendar_gateway.delete_event(item.calendar_event_id)
            item = item.model_copy(update={"calendar_event_id": "", "calendar_event_url": ""})
        self.repository.save(item)
        return LifeBotResponse("Oke, item ini sudah kubatalkan.")

    def handle_cancel_latest(self) -> LifeBotResponse:
        item = self.latest_active_item()
        if item is None:
            return LifeBotResponse("Aku belum menemukan item aktif yang bisa dibatalkan.")
        return self.handle_cancel(item.item_id)

    def handle_view(self, item_id_fragment: str) -> LifeBotResponse:
        item = self.find_item(item_id_fragment)
        return LifeBotResponse(self.rendering.render_item_detail(item), reply_context=self.item_reply_context(item))

    def handle_view_latest(self) -> LifeBotResponse:
        item = self.latest_active_item()
        if item is None:
            return LifeBotResponse("Aku belum menemukan item aktif yang bisa ditampilkan.")
        return self.handle_view(item.item_id)

    def update_item_from_parsed(
        self,
        item_id_fragment: str,
        parsed: ParsedLifeItem,
        *,
        correction_text: str,
        message_datetime: datetime | None = None,
    ) -> LifeBotResponse:
        item = self.find_item(item_id_fragment)
        updated = item.model_copy(
            update={
                "type": parsed.type,
                "title": parsed.title,
                "person": parsed.person,
                "details": parsed.details,
                "due_at": self.normalize_due_datetime(parsed, message_datetime=message_datetime),
                "remind_at": self.normalize_remind_datetime(parsed, message_datetime=message_datetime),
                "all_day": parsed.all_day,
                "recurrence": parsed.recurrence,
                "recurrence_until": parsed.recurrence_until,
                "raw_input": correction_text,
                "updated_at": self._now(),
            }
        )
        if updated.due_at is None and updated.calendar_event_id:
            self.calendar_gateway.delete_event(updated.calendar_event_id)
            updated = updated.model_copy(update={"calendar_event_id": "", "calendar_event_url": ""})
        updated, warning = self.sync_calendar(updated)
        self.repository.save(updated)
        message = self.rendering.render_item_detail(updated, heading="Item yang diperbarui")
        if warning:
            message = f"{message}\n\n{warning}"
        return LifeBotResponse(message, reply_context=self.item_reply_context(updated))

    def dispatch_due_reminders(self, *, bot) -> int:
        raise NotImplementedError("Use dispatch_due_reminders_async for reminder delivery.")

    async def dispatch_due_reminders_async(self, *, bot, chat_id: int | None) -> int:
        if chat_id is None:
            return 0
        now = self._now()
        count = 0
        for item in self.repository.list_due_for_reminder(now):
            message = self.rendering.render_due_reminder(item, fallback_time=now)
            await bot.send_message(chat_id=chat_id, text=message)
            if item.recurrence:
                next_due = advance_recurrence(item.due_at, item.recurrence, until_date=item.recurrence_until)
                if next_due is None:
                    updated = item.model_copy(
                        update={
                            "last_reminded_at": now,
                            "status": LifeItemStatus.DONE,
                            "updated_at": now,
                        }
                    )
                    if updated.calendar_event_id:
                        self.calendar_gateway.delete_event(updated.calendar_event_id)
                        updated = updated.model_copy(update={"calendar_event_id": "", "calendar_event_url": ""})
                else:
                    updated = item.model_copy(
                        update={
                            "due_at": next_due,
                            "remind_at": shift_with_same_offset(old_due_at=item.due_at, old_remind_at=item.remind_at, new_due_at=next_due),
                            "last_reminded_at": None,
                            "status": LifeItemStatus.OPEN,
                            "updated_at": now,
                        }
                    )
                    updated, _ = self.sync_calendar(updated)
            else:
                updated = item.model_copy(
                    update={
                        "last_reminded_at": now,
                        "status": LifeItemStatus.OPEN,
                        "updated_at": now,
                    }
                )
            self.repository.save(updated)
            count += 1
        return count

    def batch_needs_confirmation(self, batch: ParsedLifeBatch, *, message_datetime: datetime | None = None) -> bool:
        now = self.reference_time(message_datetime)
        for parsed in batch.items:
            item = self.create_item_from_parsed(parsed, message_datetime=message_datetime)
            scheduled_at = item.scheduled_at()
            if scheduled_at is not None and scheduled_at < now:
                return True
        return False

    def save_batch(self, batch: ParsedLifeBatch, *, message_datetime: datetime | None = None) -> LifeBotResponse:
        saved_items: list[tuple[LifeItem, str]] = []
        for parsed in batch.items:
            item = self.create_item_from_parsed(parsed, message_datetime=message_datetime)
            item = self.repository.save(item)
            item, warning = self.sync_calendar(item)
            self.repository.save(item)
            saved_items.append((item, warning))
        if len(saved_items) == 1:
            item, warning = saved_items[0]
            return LifeBotResponse(self.rendering.render_created_item(item, warning=warning), reply_context=self.item_reply_context(item))
        return LifeBotResponse(self.rendering.render_created_batch(saved_items))

    def create_item_from_parsed(
        self,
        parsed: ParsedLifeItem,
        *,
        message_datetime: datetime | None = None,
    ) -> LifeItem:
        normalized_due = self.normalize_due_datetime(parsed, message_datetime=message_datetime)
        normalized_remind = self.normalize_remind_datetime(parsed, message_datetime=message_datetime)
        now = self._now()
        return LifeItem(
            type=parsed.type,
            title=parsed.title,
            person=parsed.person,
            details=parsed.details,
            due_at=normalized_due,
            remind_at=normalized_remind,
            all_day=parsed.all_day,
            recurrence=parsed.recurrence,
            recurrence_until=parsed.recurrence_until,
            raw_input=parsed.raw_input,
            updated_at=now,
        )

    def item_reply_context(self, item: LifeItem) -> LifeReplyContext:
        return LifeReplyContext(kind="item", item_id=item.item_id)

    def active_items(self) -> list[LifeItem]:
        return [item for item in self.repository.list_all() if item.status in {LifeItemStatus.OPEN, LifeItemStatus.SNOOZED}]

    def latest_active_item(self) -> LifeItem | None:
        items = self.active_items()
        if not items:
            return None
        return max(items, key=lambda item: item.updated_at or item.created_at)

    def find_item(self, item_id_fragment: str) -> LifeItem:
        normalized = item_id_fragment.strip().lower()
        matches = [item for item in self.repository.list_all() if item.item_id.lower().endswith(normalized)]
        if not matches:
            raise ValueError(f"Item `{item_id_fragment}` was not found.")
        if len(matches) > 1:
            raise ValueError(f"Item id fragment `{item_id_fragment}` is ambiguous.")
        return matches[0]

    def sync_calendar(self, item: LifeItem) -> tuple[LifeItem, str]:
        if item.due_at is None:
            return item, ""
        try:
            result = self.calendar_gateway.upsert_item(item)
        except Exception:
            return item, (
                "Saved locally, but calendar sync failed.\n"
                "Check LIFE_GOOGLE_CALENDAR_ID and ensure the calendar is shared with the service account."
            )
        return (
            item.model_copy(
                update={
                    "calendar_event_id": result.event_id,
                    "calendar_event_url": result.html_link,
                    "updated_at": self._now(),
                }
            ),
            "",
        )

    def normalize_due_datetime(
        self,
        parsed: ParsedLifeItem,
        *,
        message_datetime: datetime | None = None,
    ) -> datetime | None:
        value = self.normalize_datetime(parsed.due_at)
        if value is None:
            return None
        return self.apply_ambiguous_time_rules(value, raw_input=parsed.raw_input, reference_time=self.reference_time(message_datetime))

    def normalize_remind_datetime(
        self,
        parsed: ParsedLifeItem,
        *,
        message_datetime: datetime | None = None,
    ) -> datetime | None:
        value = self.normalize_datetime(parsed.remind_at)
        if value is None:
            return None
        due_at = self.normalize_due_datetime(parsed, message_datetime=message_datetime)
        if parsed.due_at is not None and parsed.remind_at == parsed.due_at:
            return due_at
        return value

    def apply_ambiguous_time_rules(self, value: datetime, *, raw_input: str, reference_time: datetime) -> datetime:
        lowered = raw_input.lower()
        ambiguous_match = re.search(r"\bjam\s+([1-9]|1[01])(?:(?::|\.)\d{2})?\b", lowered)
        has_explicit_period = any(token in lowered for token in (" am", " pm", "pagi", "siang", "sore", "malam"))
        if ambiguous_match and not has_explicit_period:
            preferred_hour = int(ambiguous_match.group(1)) + 12
            value = value.replace(hour=preferred_hour)
            if not self.mentions_explicit_date(lowered) and value <= reference_time:
                value += timedelta(days=1)
        return value

    @staticmethod
    def mentions_explicit_date(text: str) -> bool:
        return bool(
            re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
            or re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b", text)
            or re.search(r"\b(today|hari ini|tomorrow|besok|next week|minggu depan)\b", text)
            or re.search(
                r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|senin|selasa|rabu|kamis|jumat|jum'at|sabtu|minggu)\b",
                text,
            )
            or re.search(r"\b\d{1,2}\s+[a-zA-Z]+\b", text)
        )

    def normalize_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=self._zone())
        return value.astimezone(self._zone())

    def reference_time(self, message_datetime: datetime | None) -> datetime:
        if message_datetime is None:
            return self._now()
        if message_datetime.tzinfo is None:
            return message_datetime.replace(tzinfo=ZoneInfo("UTC")).astimezone(self._zone())
        return message_datetime.astimezone(self._zone())

    def _now(self) -> datetime:
        return datetime.now(self._zone())

    def _zone(self) -> ZoneInfo:
        return ZoneInfo(self.default_timezone)
