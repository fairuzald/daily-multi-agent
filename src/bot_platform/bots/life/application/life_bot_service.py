from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot_platform.bots.life.domain.models import LifeItem, LifeItemStatus, LifeItemType, ParsedLifeBatch, ParsedLifeItem
from bot_platform.bots.life.domain.parser import LifeItemParser
from bot_platform.bots.life.domain.responses import LifeBotResponse
from bot_platform.bots.life.domain.scheduling import advance_recurrence, shift_with_same_offset
from bot_platform.bots.life.infrastructure.calendar_gateway import GoogleCalendarGateway
from bot_platform.bots.life.infrastructure.repositories import LifeRepository
from bot_platform.bots.life.infrastructure.state_store import LifeReplyContext, LifeStateStore, PendingLifeParseState


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

    def handle_start(self, user_id: int, chat_id: int) -> LifeBotResponse:
        self._claim_or_require_owner(user_id, chat_id)
        return LifeBotResponse(
            "Life bot is ready.\n\n"
            "What each type means:\n"
            "- task = something you must do\n"
            "- reminder = ping me at a time\n"
            "- follow_up = remind me to check back with someone\n"
            "- important_date = birthday, renewal, deadline, anniversary\n\n"
            "Good input examples:\n"
            "- pay wifi tomorrow 9am\n"
            "- remind me in 5 minutes to check transfer\n"
            "- remind me today at 20:30 to review bills\n"
            "- follow up with Aldi next Tuesday 8pm\n"
            "- mom birthday 12 May\n"
            "- rent every month\n"
            "- pay wifi tomorrow and follow up with Aldi on Friday 8pm\n\n"
            "- you can also send a voice note with the same kinds of reminders\n\n"
            "What each view shows:\n"
            "- /today = items scheduled for today\n"
            "- /upcoming = items coming in the next 7 days\n"
            "- /overdue = items already past due\n"
            "- /followups = only follow_up items\n"
            "- /dates = only important_date items\n\n"
            "Actions:\n"
            "- reply to a saved item with /done\n"
            "- reply to a saved item with /cancel or /delete\n"
            "- reply to a saved item with /snooze 2hours\n"
            "- plain text replies also work: done, cancel, delete, snooze 2hours\n"
            "- if parsing fails, reply to the bot's rewrite prompt with a clearer sentence\n\n"
            "Reminder delivery:\n"
            "- Telegram reminders are checked every 5 minutes by the reminder tick\n"
            "- Google Calendar events are created immediately when calendar sync is enabled\n"
            "- under 1 minute is not reliable for Telegram reminders\n"
            "- for quick testing, use 'in 5 minutes' or 'in 10 minutes'"
        )

    def handle_help(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        return self.handle_start(user_id, self.state_store.get_owner_chat_id() or 0)

    def handle_status(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        items = self.repository.list_all()
        open_items = [item for item in items if item.status in {LifeItemStatus.OPEN, LifeItemStatus.SNOOZED}]
        pending = self.state_store.get_pending_parse(self.state_store.get_owner_chat_id() or 0)
        return LifeBotResponse(
            f"Total items: {len(items)}\n"
            f"Open items: {len(open_items)}\n"
            f"Pending rewrite: {'yes' if pending else 'no'}\n"
            f"Calendar sync: {'on' if self.calendar_gateway.enabled() else 'off'}"
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

        if reply_context and reply_context.kind == "item":
            action_response = self._handle_inline_action(user_id, text, reply_item_id=reply_context.item_id)
            if action_response is not None:
                return action_response

        if reply_context and reply_context.kind == "pending":
            pending = self.state_store.get_pending_parse(chat_id)
            if pending is None:
                return LifeBotResponse("That pending rewrite expired. Please send the reminder again.")
            return self._handle_pending_rewrite(chat_id, pending, text, message_datetime=message_datetime)

        batch = self._parse_items(text, message_datetime=message_datetime)
        if batch.needs_manual_review or not batch.items:
            return self._queue_manual_review(chat_id, text, batch)
        return self._save_batch(batch)

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
        today = self._now().date()
        items = [
            item
            for item in self._active_items()
            if item.scheduled_at() is not None and item.scheduled_at().astimezone(self._zone()).date() == today
        ]
        return self._render_items("Today", items)

    def handle_upcoming(self, user_id: int, days: int = 7) -> LifeBotResponse:
        self._ensure_owner(user_id)
        now = self._now()
        cutoff = now + timedelta(days=days)
        items = [
            item
            for item in self._active_items()
            if item.scheduled_at() is not None and now <= item.scheduled_at().astimezone(self._zone()) <= cutoff
        ]
        return self._render_items(f"Upcoming {days} days", items)

    def handle_overdue(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        now = self._now()
        items = [
            item
            for item in self._active_items()
            if item.scheduled_at() is not None and item.scheduled_at().astimezone(self._zone()) < now
        ]
        return self._render_items("Overdue", items)

    def handle_followups(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        items = [item for item in self._active_items() if item.type == LifeItemType.FOLLOW_UP]
        return self._render_items("Follow-ups", items)

    def handle_important_dates(self, user_id: int) -> LifeBotResponse:
        self._ensure_owner(user_id)
        items = [item for item in self._active_items() if item.type == LifeItemType.IMPORTANT_DATE]
        return self._render_items("Important dates", items)

    def handle_done(self, user_id: int, item_id_fragment: str) -> LifeBotResponse:
        self._ensure_owner(user_id)
        item = self._find_item(item_id_fragment)
        now = self._now()
        if item.recurrence:
            next_due = advance_recurrence(item.due_at, item.recurrence)
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
            item, warning = self._sync_calendar(item)
            if warning:
                self.repository.save(item)
                return LifeBotResponse(f"Updated as {item.status.value}.\n{warning}")
        self.repository.save(item)
        return LifeBotResponse(f"Updated as {item.status.value}.")

    def handle_snooze(self, user_id: int, item_id_fragment: str, amount: int, unit: str) -> LifeBotResponse:
        self._ensure_owner(user_id)
        item = self._find_item(item_id_fragment)
        delta = timedelta(days=amount) if unit == "days" else timedelta(hours=amount)
        reminder_target = self._now() + delta
        item = item.model_copy(
            update={
                "status": LifeItemStatus.SNOOZED,
                "remind_at": reminder_target,
                "updated_at": self._now(),
            }
        )
        item, warning = self._sync_calendar(item)
        self.repository.save(item)
        message = f"Snoozed until {self._format_when(reminder_target, all_day=False)}."
        if warning:
            message = f"{message}\n{warning}"
        return LifeBotResponse(message)

    def handle_cancel(self, user_id: int, item_id_fragment: str) -> LifeBotResponse:
        self._ensure_owner(user_id)
        item = self._find_item(item_id_fragment)
        item = item.model_copy(update={"status": LifeItemStatus.CANCELLED, "updated_at": self._now()})
        if item.calendar_event_id:
            self.calendar_gateway.delete_event(item.calendar_event_id)
            item = item.model_copy(update={"calendar_event_id": "", "calendar_event_url": ""})
        self.repository.save(item)
        return LifeBotResponse("Cancelled.")

    def handle_delete(self, user_id: int, item_id_fragment: str) -> LifeBotResponse:
        return self.handle_cancel(user_id, item_id_fragment)

    def item_reply_context(self, item: LifeItem) -> LifeReplyContext:
        return LifeReplyContext(kind="item", item_id=item.item_id)

    def pending_reply_context(self) -> LifeReplyContext:
        return LifeReplyContext(kind="pending")

    def dispatch_due_reminders(self, *, bot) -> int:
        chat_id = self.state_store.get_owner_chat_id()
        if chat_id is None:
            return 0
        now = self._now()
        count = 0
        for item in self.repository.list_due_for_reminder(now):
            message = self._render_due_reminder(item)
            bot.send_message(chat_id=chat_id, text=message)
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

    def _handle_pending_rewrite(
        self,
        chat_id: int,
        pending: PendingLifeParseState,
        rewrite_text: str,
        *,
        message_datetime: datetime | None,
    ) -> LifeBotResponse:
        normalized = " ".join(rewrite_text.strip().lower().split())
        if normalized in {"cancel", "/cancel", "delete", "/delete"}:
            self.state_store.clear_pending_parse(chat_id)
            return LifeBotResponse("Pending rewrite cleared.")
        batch = self._correct_items(pending.raw_input, rewrite_text, message_datetime=message_datetime)
        if batch.needs_manual_review or not batch.items:
            return self._queue_manual_review(chat_id, pending.raw_input, batch, correction_text=rewrite_text)
        self.state_store.clear_pending_parse(chat_id)
        return self._save_batch(batch)

    def _parse_items(self, text: str, *, message_datetime: datetime | None) -> ParsedLifeBatch:
        if self.ai_client is None:
            return ParsedLifeBatch(items=[self.parser.parse(text, message_datetime=message_datetime)])
        reference_time = self._reference_time(message_datetime)
        return self.ai_client.parse_life_items(
            text,
            reference_time_iso=reference_time.isoformat(),
            timezone_name=self.default_timezone,
        )

    def _correct_items(self, original_input: str, correction_input: str, *, message_datetime: datetime | None) -> ParsedLifeBatch:
        if self.ai_client is None:
            return ParsedLifeBatch(items=[self.parser.parse(correction_input, message_datetime=message_datetime)])
        reference_time = self._reference_time(message_datetime)
        return self.ai_client.correct_life_items(
            original_input=original_input,
            correction_input=correction_input,
            reference_time_iso=reference_time.isoformat(),
            timezone_name=self.default_timezone,
        )

    def _save_batch(self, batch: ParsedLifeBatch) -> LifeBotResponse:
        saved_items: list[tuple[LifeItem, str]] = []
        for parsed in batch.items:
            item = self._create_item_from_parsed(parsed)
            item = self.repository.save(item)
            item, warning = self._sync_calendar(item)
            self.repository.save(item)
            saved_items.append((item, warning))
        if len(saved_items) == 1:
            item, warning = saved_items[0]
            return LifeBotResponse(self._render_created_item(item, warning=warning), reply_context=self.item_reply_context(item))
        return LifeBotResponse(self._render_created_batch(saved_items))

    def _create_item_from_parsed(self, parsed: ParsedLifeItem) -> LifeItem:
        normalized_due = self._normalize_datetime(parsed.due_at)
        normalized_remind = self._normalize_datetime(parsed.remind_at)
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
            raw_input=parsed.raw_input,
            updated_at=now,
        )

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
            "I couldn't parse that safely yet.",
            "Reply to this message with a clearer rewrite and I'll try again.",
            "",
            "Good rewrite examples:",
            "- pay wifi tomorrow 9am",
            "- follow up with Aldi next Tuesday 8pm",
            "- mom birthday 12 May",
        ]
        if batch.manual_guidance:
            lines.insert(1, batch.manual_guidance)
        return LifeBotResponse("\n".join(lines), reply_context=self.pending_reply_context())

    def _claim_or_require_owner(self, user_id: int, chat_id: int) -> None:
        owner = self.state_store.get_owner_user_id()
        if owner is None:
            self.state_store.set_owner_user_id(user_id)
            self.state_store.set_owner_chat_id(chat_id)
            return
        if owner != user_id:
            raise PermissionError("This bot is locked to a different Telegram user.")
        self.state_store.set_owner_chat_id(chat_id)

    def _ensure_owner(self, user_id: int) -> None:
        owner = self.state_store.get_owner_user_id()
        if owner != user_id:
            raise PermissionError("This bot is locked to a different Telegram user.")

    def _find_item(self, item_id_fragment: str) -> LifeItem:
        normalized = item_id_fragment.strip().lower()
        matches = [item for item in self.repository.list_all() if item.item_id.lower().endswith(normalized)]
        if not matches:
            raise ValueError(f"Item `{item_id_fragment}` was not found.")
        if len(matches) > 1:
            raise ValueError(f"Item id fragment `{item_id_fragment}` is ambiguous.")
        return matches[0]

    def _active_items(self) -> list[LifeItem]:
        return [item for item in self.repository.list_all() if item.status in {LifeItemStatus.OPEN, LifeItemStatus.SNOOZED}]

    def _sync_calendar(self, item: LifeItem) -> tuple[LifeItem, str]:
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

    def _render_created_item(self, item: LifeItem, *, warning: str = "") -> str:
        lines = [f"Saved as {item.type.value}:", f"- {item.title}"]
        if item.person:
            lines.append(f"- Person: {item.person}")
        if item.due_at is not None:
            lines.append(f"- Scheduled: {self._format_when(item.due_at, all_day=item.all_day)}")
        if item.recurrence:
            lines.append(f"- Recurs: {item.recurrence}")
        if item.calendar_event_url:
            lines.append(f"- Calendar: {item.calendar_event_url}")
        elif item.calendar_event_id:
            lines.append("- Calendar: synced")
        if warning:
            lines.append("")
            lines.append(warning)
        return "\n".join(lines)

    def _render_created_batch(self, items: list[tuple[LifeItem, str]]) -> str:
        lines = [f"Saved {len(items)} items:"]
        for item, warning in items:
            lines.append(f"- {item.title} [{item.type.value}]")
            if item.due_at is not None:
                lines.append(f"  Scheduled: {self._format_when(item.due_at, all_day=item.all_day)}")
            if item.calendar_event_url:
                lines.append(f"  Calendar: {item.calendar_event_url}")
            if warning:
                lines.append(f"  Warning: {warning.replace(chr(10), ' ')}")
        return "\n".join(lines)

    def _render_items(self, heading: str, items: list[LifeItem]) -> LifeBotResponse:
        if not items:
            return LifeBotResponse(f"{heading}: no items.")
        lines = [f"{heading}:"]
        for item in sorted(items, key=lambda value: value.scheduled_at() or value.created_at):
            when = self._format_when(item.scheduled_at() or item.created_at, all_day=item.all_day if item.scheduled_at() else False)
            suffix = f" [{item.type.value}]"
            if item.calendar_event_url:
                suffix = f"{suffix} calendar"
            lines.append(f"- {item.title}{suffix} - {when}")
        return LifeBotResponse("\n".join(lines))

    def _render_due_reminder(self, item: LifeItem) -> str:
        return (
            f"Reminder\n"
            f"- {item.title}\n"
            f"- Type: {item.type.value}\n"
            f"- Scheduled: {self._format_when(item.scheduled_at() or self._now(), all_day=item.all_day)}"
        )

    def _handle_inline_action(self, user_id: int, text: str, *, reply_item_id: str) -> LifeBotResponse | None:
        normalized = " ".join(text.strip().lower().split())
        if not reply_item_id:
            return None
        if normalized in {"done", "/done", "mark done"}:
            return self.handle_done(user_id, reply_item_id)
        if normalized in {"cancel", "/cancel", "delete", "/delete"}:
            return self.handle_cancel(user_id, reply_item_id)
        if normalized.startswith("snooze ") or normalized.startswith("/snooze "):
            amount_text = "".join(ch for ch in normalized if ch.isdigit())
            if not amount_text:
                return LifeBotResponse("Reply to an item and send `snooze 2hours` or `snooze 2days`.")
            unit = "days" if "day" in normalized else "hours"
            return self.handle_snooze(user_id, reply_item_id, int(amount_text), unit)
        return None

    def _normalize_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=self._zone())
        return value.astimezone(self._zone())

    def _reference_time(self, message_datetime: datetime | None) -> datetime:
        if message_datetime is None:
            return self._now()
        if message_datetime.tzinfo is None:
            return message_datetime.replace(tzinfo=ZoneInfo("UTC")).astimezone(self._zone())
        return message_datetime.astimezone(self._zone())

    def _format_when(self, value: datetime, *, all_day: bool) -> str:
        localized = value.astimezone(self._zone())
        if all_day:
            return localized.strftime("%Y-%m-%d")
        return localized.strftime("%Y-%m-%d %H:%M")

    def _now(self) -> datetime:
        return datetime.now(self._zone())

    def _zone(self) -> ZoneInfo:
        return ZoneInfo(self.default_timezone)
