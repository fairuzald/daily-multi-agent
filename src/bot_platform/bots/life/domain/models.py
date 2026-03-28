from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class LifeItemType(str, Enum):
    TASK = "task"
    REMINDER = "reminder"
    FOLLOW_UP = "follow_up"
    IMPORTANT_DATE = "important_date"


class LifeItemStatus(str, Enum):
    OPEN = "open"
    DONE = "done"
    SNOOZED = "snoozed"
    CANCELLED = "cancelled"


class ParsedLifeItem(BaseModel):
    type: LifeItemType
    title: str
    person: str = ""
    details: str = ""
    due_at: datetime | None = None
    remind_at: datetime | None = None
    all_day: bool = True
    recurrence: str = ""
    raw_input: str


class ParsedLifeBatch(BaseModel):
    items: list[ParsedLifeItem] = Field(default_factory=list)
    needs_manual_review: bool = False
    manual_guidance: str = ""


class LifeItem(BaseModel):
    item_id: str = Field(default_factory=lambda: f"life_{uuid4().hex[:10]}")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    type: LifeItemType
    status: LifeItemStatus = LifeItemStatus.OPEN
    title: str
    person: str = ""
    details: str = ""
    due_at: datetime | None = None
    remind_at: datetime | None = None
    all_day: bool = True
    recurrence: str = ""
    raw_input: str = ""
    calendar_event_id: str = ""
    calendar_event_url: str = ""
    last_reminded_at: datetime | None = None

    def scheduled_at(self) -> datetime | None:
        return self.remind_at or self.due_at
