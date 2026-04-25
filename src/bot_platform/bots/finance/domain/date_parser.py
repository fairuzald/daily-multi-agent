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

NUMBER_WORDS = {
    "nol": 0,
    "zero": 0,
    "satu": 1,
    "one": 1,
    "dua": 2,
    "two": 2,
    "tiga": 3,
    "three": 3,
    "empat": 4,
    "four": 4,
    "lima": 5,
    "five": 5,
    "enam": 6,
    "six": 6,
    "tujuh": 7,
    "seven": 7,
    "delapan": 8,
    "eight": 8,
    "sembilan": 9,
    "nine": 9,
    "sepuluh": 10,
    "ten": 10,
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
            (r"\b(yesterday|kemarin|kemaren)\b", base_date - timedelta(days=1)),
            (r"\b(lusa)\b", base_date + timedelta(days=2)),
            (r"\b(tomorrow|besok)\b", base_date + timedelta(days=1)),
            (r"\b(tadi|barusan|just now|earlier today)\b", base_date),
            (r"\b(minggu lalu|last week)\b", base_date - timedelta(days=7)),
        ]
        for pattern, resolved in relative_patterns:
            for match in re.finditer(pattern, lowered):
                candidates.append((resolved, match.group(0)))

        candidates.extend(self._resolve_relative_counted_ranges(lowered, base_date))

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

    @classmethod
    def _resolve_relative_counted_ranges(cls, lowered: str, base_date: date) -> list[tuple[date, str]]:
        candidates: list[tuple[date, str]] = []
        patterns = (
            r"\b(?P<count>\d+|[a-zA-Z]+)\s+(?P<unit>hari|day|days)\s+(?:yang\s+|yg\s+)?lalu\b",
            r"\b(?P<count>\d+|[a-zA-Z]+)\s+(?P<unit>minggu|week|weeks)\s+(?:yang\s+|yg\s+)?lalu\b",
            r"\b(?P<count>\d+|[a-zA-Z]+)\s+(?P<unit>bulan|month|months)\s+(?:yang\s+|yg\s+)?lalu\b",
            r"\b(?P<count>\d+|[a-zA-Z]+)\s+(?P<unit>hari|day|days)\s+ago\b",
            r"\b(?P<count>\d+|[a-zA-Z]+)\s+(?P<unit>minggu|week|weeks)\s+ago\b",
            r"\b(?P<count>\d+|[a-zA-Z]+)\s+(?P<unit>bulan|month|months)\s+ago\b",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, lowered):
                count = cls._parse_count(match.group("count"))
                if count is None or count < 0:
                    continue
                resolved = cls._shift_date_back(base_date, count=count, unit=match.group("unit"))
                candidates.append((resolved, match.group(0)))
        return candidates

    @staticmethod
    def _parse_count(value: str) -> int | None:
        normalized = value.strip().lower()
        if normalized.isdigit():
            return int(normalized)
        return NUMBER_WORDS.get(normalized)

    @staticmethod
    def _shift_date_back(base_date: date, *, count: int, unit: str) -> date:
        normalized_unit = unit.strip().lower()
        if normalized_unit in {"hari", "day", "days"}:
            return base_date - timedelta(days=count)
        if normalized_unit in {"minggu", "week", "weeks"}:
            return base_date - timedelta(days=count * 7)
        if normalized_unit in {"bulan", "month", "months"}:
            year = base_date.year
            month = base_date.month - count
            while month <= 0:
                year -= 1
                month += 12
            day = min(base_date.day, _days_in_month(year, month))
            return date(year, month, day)
        return base_date


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year if month < 12 else year + 1, month % 12 + 1, 1) - timedelta(days=1)).day
