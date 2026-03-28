from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .models import LifeItemType, ParsedLifeItem


MONTHS = {
    "jan": 1,
    "january": 1,
    "januari": 1,
    "feb": 2,
    "february": 2,
    "februari": 2,
    "mar": 3,
    "march": 3,
    "maret": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "mei": 5,
    "jun": 6,
    "june": 6,
    "juni": 6,
    "jul": 7,
    "july": 7,
    "juli": 7,
    "aug": 8,
    "august": 8,
    "agustus": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "okt": 10,
    "oktober": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
    "des": 12,
    "desember": 12,
}

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


class LifeItemParser:
    def __init__(self, timezone_name: str = "Asia/Jakarta") -> None:
        self.timezone_name = timezone_name

    def parse(self, text: str, *, message_datetime: datetime | None = None) -> ParsedLifeItem:
        normalized = " ".join(text.strip().split())
        item_type = self._detect_type(normalized)
        due_at, matched_date_text, all_day = self._extract_datetime(normalized, message_datetime=message_datetime)
        recurrence, matched_recurrence_text = self._extract_recurrence(normalized)
        person = self._extract_person(normalized, item_type)
        title = self._build_title(
            normalized,
            item_type=item_type,
            matched_date_text=matched_date_text,
            matched_recurrence_text=matched_recurrence_text,
        )
        remind_at = due_at
        if item_type == LifeItemType.IMPORTANT_DATE and due_at is not None:
            remind_at = due_at - timedelta(days=1)
        return ParsedLifeItem(
            type=item_type,
            title=title or normalized,
            person=person,
            due_at=due_at,
            remind_at=remind_at,
            all_day=all_day,
            recurrence=recurrence,
            raw_input=text,
        )

    def _detect_type(self, text: str) -> LifeItemType:
        lowered = text.lower()
        if lowered.startswith(("remind me", "ingatkan", "ingatkan aku")):
            return LifeItemType.REMINDER
        if "follow up with" in lowered or "follow-up with" in lowered or "follow up " in lowered:
            return LifeItemType.FOLLOW_UP
        if any(token in lowered for token in ("birthday", "ulang tahun", "renewal", "deadline", "jatuh tempo", "anniversary")):
            return LifeItemType.IMPORTANT_DATE
        return LifeItemType.TASK

    def _reference_now(self, message_datetime: datetime | None) -> datetime:
        zone = ZoneInfo(self.timezone_name)
        if message_datetime is None:
            return datetime.now(zone)
        if message_datetime.tzinfo is None:
            return message_datetime.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)
        return message_datetime.astimezone(zone)

    def _extract_datetime(self, text: str, *, message_datetime: datetime | None) -> tuple[datetime | None, str, bool]:
        now = self._reference_now(message_datetime)
        lowered = text.lower()
        matched_text = ""
        all_day = True
        due_date: datetime | None = None

        relative_minutes = re.search(r"\bin\s+(\d+)\s+minutes?\b|\b(\d+)\s+menit\s+lagi\b", lowered)
        if relative_minutes:
            amount = int(relative_minutes.group(1) or relative_minutes.group(2))
            due_date = now + timedelta(minutes=amount)
            matched_text = relative_minutes.group(0)
            all_day = False

        relative_hours = re.search(r"\bin\s+(\d+)\s+hours?\b|\b(\d+)\s+jam\s+lagi\b", lowered)
        if due_date is None and relative_hours:
            amount = int(relative_hours.group(1) or relative_hours.group(2))
            due_date = now + timedelta(hours=amount)
            matched_text = relative_hours.group(0)
            all_day = False

        in_days = re.search(r"\bin\s+(\d+)\s+days\b|\b(\d+)\s+hari\s+lagi\b", lowered)
        if due_date is None and in_days:
            amount = int(in_days.group(1) or in_days.group(2))
            due_date = now + timedelta(days=amount)
            matched_text = in_days.group(0)

        explicit = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", lowered)
        if explicit:
            due_date = datetime(int(explicit.group(1)), int(explicit.group(2)), int(explicit.group(3)), tzinfo=now.tzinfo)
            matched_text = explicit.group(0)

        if due_date is None:
            slash = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", lowered)
            if slash:
                due_date = datetime(int(slash.group(3)), int(slash.group(2)), int(slash.group(1)), tzinfo=now.tzinfo)
                matched_text = slash.group(0)

        if due_date is None:
            month_match = re.search(r"\b(\d{1,2})\s+([a-zA-Z]+)(?:\s+(\d{4}))?\b", lowered)
            if month_match:
                month_number = MONTHS.get(month_match.group(2).lower())
                if month_number is not None:
                    year = int(month_match.group(3) or now.year)
                    due_date = datetime(year, month_number, int(month_match.group(1)), tzinfo=now.tzinfo)
                    if due_date.date() < now.date() and month_match.group(3) is None:
                        due_date = due_date.replace(year=year + 1)
                    matched_text = month_match.group(0)

        if due_date is None:
            relative_patterns = (
                ("today", now),
                ("hari ini", now),
                ("tomorrow", now + timedelta(days=1)),
                ("besok", now + timedelta(days=1)),
                ("next week", now + timedelta(days=7)),
                ("minggu depan", now + timedelta(days=7)),
            )
            for label, resolved in relative_patterns:
                if label in lowered:
                    due_date = resolved
                    matched_text = label
                    break

        if due_date is None:
            next_weekday_match = re.search(r"\bnext\s+([a-zA-Z']+)\b", lowered)
            if next_weekday_match:
                weekday_name = next_weekday_match.group(1).lower()
                if weekday_name in WEEKDAYS:
                    delta = (WEEKDAYS[weekday_name] - now.weekday()) % 7
                    delta = 7 if delta == 0 else delta
                    due_date = now + timedelta(days=delta)
                    matched_text = next_weekday_match.group(0).strip()

        if due_date is None:
            weekday_names = "|".join(re.escape(name) for name in WEEKDAYS)
            weekday_match = re.search(rf"\b({weekday_names})\b", lowered)
            if weekday_match:
                weekday_name = weekday_match.group(1).lower()
                delta = (WEEKDAYS[weekday_name] - now.weekday()) % 7
                due_date = now + timedelta(days=delta)
                matched_text = weekday_match.group(0).strip()

        time_match = re.search(
            r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b"
            r"|\bjam\s*(\d{1,2})(?::|\.?)(\d{2})?\b"
            r"|\bat\s+(\d{1,2})(?::(\d{2}))\b",
            lowered,
        )
        if time_match:
            hour_text = time_match.group(1) or time_match.group(4) or time_match.group(6)
            minute_text = time_match.group(2) or time_match.group(5) or time_match.group(7) or "0"
            meridiem = time_match.group(3)
            hour = int(hour_text)
            minute = int(minute_text)
            if meridiem:
                meridiem = meridiem.lower()
                if meridiem == "pm" and hour < 12:
                    hour += 12
                if meridiem == "am" and hour == 12:
                    hour = 0
            if due_date is None:
                due_date = now
            due_date = due_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            all_day = False
            matched_text = f"{matched_text} {time_match.group(0)}".strip()

        if due_date is None:
            return None, "", True

        if all_day:
            due_date = due_date.replace(hour=9, minute=0, second=0, microsecond=0)
        return due_date, matched_text.strip(), all_day

    def _extract_recurrence(self, text: str) -> tuple[str, str]:
        lowered = text.lower()
        direct_map = {
            "every day": "daily",
            "setiap hari": "daily",
            "every week": "weekly",
            "setiap minggu": "weekly",
            "every month": "monthly",
            "setiap bulan": "monthly",
            "every year": "yearly",
            "setiap tahun": "yearly",
        }
        for pattern, recurrence in direct_map.items():
            if pattern in lowered:
                return recurrence, pattern

        weekday_match = re.search(r"\bevery\s+([a-zA-Z']+)\b|\bsetiap\s+([a-zA-Z']+)\b", lowered)
        if weekday_match:
            weekday_name = (weekday_match.group(1) or weekday_match.group(2) or "").lower()
            if weekday_name in WEEKDAYS:
                return f"weekday:{weekday_name}", weekday_match.group(0)
        return "", ""

    def _extract_person(self, text: str, item_type: LifeItemType) -> str:
        lowered = text.lower()
        if item_type == LifeItemType.FOLLOW_UP:
            match = re.search(
                r"follow(?:-|\s)?up(?:\swith)?\s+([a-zA-Z0-9 _-]+?)(?:\s+(?:on|at|today|tomorrow|besok|next|in|monday|tuesday|wednesday|thursday|friday|saturday|sunday|senin|selasa|rabu|kamis|jumat|sabtu|minggu)\b|$)",
                lowered,
            )
            if match:
                return match.group(1).strip().title()
        return ""

    def _build_title(
        self,
        text: str,
        *,
        item_type: LifeItemType,
        matched_date_text: str,
        matched_recurrence_text: str,
    ) -> str:
        title = text
        prefixes = {
            LifeItemType.REMINDER: (r"^remind me to\s+", r"^ingatkan(?: aku)?\s+"),
            LifeItemType.FOLLOW_UP: (r"^follow(?:-|\s)?up(?: with)?\s+",),
        }
        for pattern in prefixes.get(item_type, ()):
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)
        if matched_date_text:
            title = re.sub(re.escape(matched_date_text), "", title, flags=re.IGNORECASE)
        if matched_recurrence_text:
            title = re.sub(re.escape(matched_recurrence_text), "", title, flags=re.IGNORECASE)
        title = re.sub(r"\bin\s+\d+\s+(minutes?|hours?|days?)\b", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\b\d+\s+(menit|jam|hari)\s+lagi\b", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s+", " ", title).strip(" ,.-")
        return title
