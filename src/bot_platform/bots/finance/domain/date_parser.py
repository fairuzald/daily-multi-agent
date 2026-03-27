from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


WEEKDAYS = {
    "monday": 0,
    "senin": 0,
    "tuesday": 1,
    "selasa": 1,
    "wednesday": 2,
    "rabu": 2,
    "thursday": 3,
    "kamis": 3,
    "friday": 4,
    "jumat": 4,
    "jum'at": 4,
    "saturday": 5,
    "sabtu": 5,
    "sunday": 6,
    "minggu": 6,
}


@dataclass(frozen=True)
class DateResolution:
    resolved_date: date | None
    matched_text: str = ""
    ambiguous: bool = False


class DateParser:
    def __init__(self, timezone_name: str = "Asia/Jakarta") -> None:
        self.timezone_name = timezone_name

    def reference_date(self, message_datetime: datetime | None) -> date:
        if message_datetime is None:
            return datetime.now(ZoneInfo(self.timezone_name)).date()
        if message_datetime.tzinfo is None:
            message_datetime = message_datetime.replace(tzinfo=ZoneInfo("UTC"))
        return message_datetime.astimezone(ZoneInfo(self.timezone_name)).date()

    def resolve(self, text: str, *, message_datetime: datetime | None = None) -> DateResolution:
        base_date = self.reference_date(message_datetime)
        lowered = text.lower()
        candidates: list[tuple[date, str]] = []

        for pattern in (r"\b(\d{4}-\d{2}-\d{2})\b",):
            for match in re.finditer(pattern, lowered):
                candidates.append((date.fromisoformat(match.group(1)), match.group(1)))

        for pattern in (r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b"):
            for match in re.finditer(pattern, lowered):
                day_value, month_value, year_value = match.groups()
                candidates.append((date(int(year_value), int(month_value), int(day_value)), match.group(0)))

        relative_patterns = [
            (r"\b(today|hari ini)\b", base_date),
            (r"\b(yesterday|kemarin)\b", base_date - timedelta(days=1)),
            (r"\b(lusa)\b", base_date + timedelta(days=2)),
            (r"\b(tomorrow|besok)\b", base_date + timedelta(days=1)),
            (r"\b(minggu lalu|last week)\b", base_date - timedelta(days=7)),
        ]
        for pattern, resolved in relative_patterns:
            for match in re.finditer(pattern, lowered):
                candidates.append((resolved, match.group(0)))

        for match in re.finditer(r"\b(\d+)\s+hari\s+lalu\b", lowered):
            candidates.append((base_date - timedelta(days=int(match.group(1))), match.group(0)))

        for match in re.finditer(r"\b(last\s+)?([a-zA-Z']+)\s+lalu\b|\blast\s+([a-zA-Z']+)\b", lowered):
            weekday_name = (match.group(2) or match.group(3) or "").strip()
            weekday_index = WEEKDAYS.get(weekday_name)
            if weekday_index is None:
                continue
            delta = (base_date.weekday() - weekday_index) % 7
            delta = 7 if delta == 0 else delta
            candidates.append((base_date - timedelta(days=delta), match.group(0)))

        if not candidates:
            return DateResolution(resolved_date=base_date)

        unique_dates = {item[0] for item in candidates}
        if len(unique_dates) > 1:
            return DateResolution(resolved_date=None, matched_text=", ".join(item[1] for item in candidates), ambiguous=True)

        return DateResolution(resolved_date=candidates[0][0], matched_text=candidates[0][1], ambiguous=False)
