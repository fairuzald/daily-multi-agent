from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bot_platform.bots.life.domain.models import LifeItem


@dataclass(frozen=True)
class CalendarSyncResult:
    event_id: str = ""
    html_link: str = ""


class GoogleCalendarGateway:
    def __init__(self, service_account_json: str, calendar_id: str, timezone_name: str = "Asia/Jakarta") -> None:
        self.service_account_json = service_account_json
        self.calendar_id = calendar_id
        self.timezone_name = timezone_name

    def enabled(self) -> bool:
        return bool(self.service_account_json.strip() and self.calendar_id.strip())

    def upsert_item(self, item: LifeItem) -> CalendarSyncResult:
        if not self.enabled() or item.due_at is None:
            return CalendarSyncResult(event_id=item.calendar_event_id, html_link=item.calendar_event_url)
        session = self._authorized_session()
        event_body = self._build_event_payload(item)
        if item.calendar_event_id:
            response = session.patch(self._event_url(item.calendar_event_id), json=event_body, timeout=30)
        else:
            response = session.post(self._events_url(), json=event_body, timeout=30)
        response.raise_for_status()
        payload = response.json()
        return CalendarSyncResult(
            event_id=str(payload.get("id") or item.calendar_event_id),
            html_link=str(payload.get("htmlLink") or item.calendar_event_url or ""),
        )

    def delete_event(self, event_id: str) -> None:
        if not self.enabled() or not event_id:
            return
        session = self._authorized_session()
        response = session.delete(self._event_url(event_id), timeout=30)
        if response.status_code not in {200, 204, 404}:
            response.raise_for_status()

    def _authorized_session(self):
        try:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2.service_account import Credentials
        except ImportError as exc:
            raise RuntimeError("google-auth is required for Google Calendar integration.") from exc

        info = json.loads(self.service_account_json)
        credentials = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        return AuthorizedSession(credentials)

    def _events_url(self) -> str:
        from urllib.parse import quote

        return f"https://www.googleapis.com/calendar/v3/calendars/{quote(self.calendar_id, safe='')}/events"

    def _event_url(self, event_id: str) -> str:
        from urllib.parse import quote

        return f"{self._events_url()}/{quote(event_id, safe='')}"

    def _build_event_payload(self, item: LifeItem) -> dict[str, Any]:
        description_lines = [f"Type: {item.type.value}", f"Item ID: {item.item_id}"]
        if item.person:
            description_lines.append(f"Person: {item.person}")
        if item.details:
            description_lines.append(f"Details: {item.details}")
        if item.raw_input:
            description_lines.append(f"Captured from: {item.raw_input}")

        payload: dict[str, Any] = {
            "summary": item.title,
            "description": "\n".join(description_lines),
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]},
        }
        if item.all_day:
            start_date = item.due_at.date()
            payload["start"] = {"date": start_date.isoformat()}
            payload["end"] = {"date": (start_date + timedelta(days=1)).isoformat()}
        else:
            end_at = item.due_at + timedelta(minutes=30)
            payload["start"] = {"dateTime": item.due_at.isoformat(), "timeZone": self.timezone_name}
            payload["end"] = {"dateTime": end_at.isoformat(), "timeZone": self.timezone_name}
        if item.recurrence:
            recurrence_map = {
                "daily": "RRULE:FREQ=DAILY",
                "weekly": "RRULE:FREQ=WEEKLY",
                "monthly": "RRULE:FREQ=MONTHLY",
                "yearly": "RRULE:FREQ=YEARLY",
            }
            recurrence_rule = ""
            if item.recurrence.startswith("weekday:"):
                day = item.recurrence.split(":", 1)[1][:2].upper()
                recurrence_rule = f"RRULE:FREQ=WEEKLY;BYDAY={day}"
            elif item.recurrence in recurrence_map:
                recurrence_rule = recurrence_map[item.recurrence]
            if recurrence_rule:
                if item.recurrence_until is not None:
                    until_local = datetime.combine(
                        item.recurrence_until,
                        time(23, 59, 59),
                        tzinfo=ZoneInfo(self.timezone_name),
                    )
                    until_utc = until_local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    recurrence_rule = f"{recurrence_rule};UNTIL={until_utc}"
                payload["recurrence"] = [recurrence_rule]
        return payload
