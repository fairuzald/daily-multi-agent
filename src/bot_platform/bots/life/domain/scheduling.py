from __future__ import annotations

from datetime import datetime, timedelta


def advance_recurrence(current_due_at: datetime | None, recurrence: str) -> datetime | None:
    if current_due_at is None or not recurrence:
        return None
    normalized = recurrence.strip().lower()
    if normalized == "daily":
        return current_due_at + timedelta(days=1)
    if normalized == "weekly":
        return current_due_at + timedelta(weeks=1)
    if normalized == "monthly":
        return current_due_at + timedelta(days=30)
    if normalized == "yearly":
        return current_due_at + timedelta(days=365)
    if normalized.startswith("weekday:"):
        return current_due_at + timedelta(weeks=1)
    return None


def shift_with_same_offset(
    *,
    old_due_at: datetime | None,
    old_remind_at: datetime | None,
    new_due_at: datetime | None,
) -> datetime | None:
    if old_due_at is None or old_remind_at is None or new_due_at is None:
        return new_due_at
    return new_due_at + (old_remind_at - old_due_at)
