from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bot_platform.bots.life.domain.models import LifeItem
from bot_platform.bots.life.domain.responses import LifeBotResponse


class LifeRenderingService:
    def __init__(self, default_timezone: str = "Asia/Jakarta") -> None:
        self.default_timezone = default_timezone

    def render_created_item(self, item: LifeItem, *, warning: str = "") -> str:
        lines = [f"Sudah kusimpan sebagai {item.type.value}:", f"- {item.title}"]
        if item.person:
            lines.append(f"- Orang: {item.person}")
        if item.details:
            lines.append(f"- Detail: {item.details}")
        if item.due_at is not None:
            lines.append(f"- Waktu: {self.format_when(item.due_at, all_day=item.all_day)}")
        if item.recurrence:
            lines.append(f"- Berulang: {self._format_recurrence(item)}")
        if item.calendar_event_url:
            lines.append(f"- Kalender: {item.calendar_event_url}")
        elif item.calendar_event_id:
            lines.append("- Kalender: tersinkron")
        if warning:
            lines.append("")
            lines.append(warning)
        return "\n".join(lines)

    def render_created_batch(self, items: list[tuple[LifeItem, str]]) -> str:
        lines = [f"Sudah kusimpan {len(items)} item:"]
        for item, warning in items:
            lines.append(f"- {item.title} [{item.type.value}]")
            if item.due_at is not None:
                lines.append(f"  Waktu: {self.format_when(item.due_at, all_day=item.all_day)}")
            if item.calendar_event_url:
                lines.append(f"  Kalender: {item.calendar_event_url}")
            if warning:
                lines.append(f"  Catatan: {warning.replace(chr(10), ' ')}")
        return "\n".join(lines)

    def render_items(self, heading: str, items: list[LifeItem]) -> LifeBotResponse:
        if not items:
            return LifeBotResponse(f"{heading}: belum ada item.")
        lines = [f"{heading}:"]
        for item in sorted(items, key=lambda value: value.scheduled_at() or value.created_at):
            when = self.format_when(item.scheduled_at() or item.created_at, all_day=item.all_day if item.scheduled_at() else False)
            suffix = f" [{item.type.value}]"
            if item.calendar_event_url:
                suffix = f"{suffix} calendar"
            lines.append(f"- {item.title}{suffix} - {when}")
        return LifeBotResponse("\n".join(lines))

    def render_due_reminder(self, item: LifeItem, *, fallback_time: datetime) -> str:
        return (
            f"Pengingat\n"
            f"- {item.title}\n"
            f"- Jenis: {item.type.value}\n"
            f"- Waktu: {self.format_when(item.scheduled_at() or fallback_time, all_day=item.all_day)}"
        )

    def render_item_detail(self, item: LifeItem, *, heading: str = "Detail item") -> str:
        lines = [
            f"{heading}:",
            f"- Judul: {item.title}",
            f"- Jenis: {item.type.value}",
            f"- Status: {item.status.value}",
            f"- ID: {item.item_id}",
        ]
        if item.person:
            lines.append(f"- Orang: {item.person}")
        if item.details:
            lines.append(f"- Detail: {item.details}")
        if item.due_at is not None:
            lines.append(f"- Waktu: {self.format_when(item.due_at, all_day=item.all_day)}")
        if item.remind_at is not None and item.remind_at != item.due_at:
            lines.append(f"- Pengingat: {self.format_when(item.remind_at, all_day=False)}")
        if item.recurrence:
            lines.append(f"- Berulang: {self._format_recurrence(item)}")
        if item.calendar_event_url:
            lines.append(f"- Kalender: {item.calendar_event_url}")
        elif item.calendar_event_id:
            lines.append("- Kalender: tersinkron")
        if item.raw_input:
            lines.append(f"- Asal input: {item.raw_input}")
        return "\n".join(lines)

    def format_when(self, value: datetime, *, all_day: bool) -> str:
        localized = value.astimezone(self._zone())
        if all_day:
            return localized.strftime("%Y-%m-%d")
        return localized.strftime("%Y-%m-%d %H:%M")

    def _zone(self) -> ZoneInfo:
        return ZoneInfo(self.default_timezone)

    @staticmethod
    def _format_recurrence(item: LifeItem) -> str:
        recurrence = item.recurrence
        if item.recurrence_until is None:
            return recurrence
        return f"{recurrence} until {item.recurrence_until.isoformat()}"
