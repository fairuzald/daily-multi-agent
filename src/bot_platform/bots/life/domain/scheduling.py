from __future__ import annotations

from datetime import date, datetime, timedelta


def advance_recurrence(current_due_at: datetime | None, recurrence: str, *, until_date: date | None = None) -> datetime | None:
    if current_due_at is None or not recurrence:
        return None
    normalized = recurrence.strip().lower()
    next_due: datetime | None = None
    if normalized == "daily":
        next_due = current_due_at + timedelta(days=1)
    elif normalized == "weekly":
        next_due = current_due_at + timedelta(weeks=1)
    elif normalized == "monthly":
        next_due = current_due_at + timedelta(days=30)
    elif normalized == "yearly":
        next_due = current_due_at + timedelta(days=365)
    elif normalized.startswith("weekday:"):
        next_due = current_due_at + timedelta(weeks=1)
    if next_due is None:
        return None
    if until_date is not None and next_due.date() > until_date:
        return None
    return next_due


def shift_with_same_offset(
    *,
    old_due_at: datetime | None,
    old_remind_at: datetime | None,
    new_due_at: datetime | None,
) -> datetime | None:
    if old_due_at is None or old_remind_at is None or new_due_at is None:
        return new_due_at
    return new_due_at + (old_remind_at - old_due_at)
