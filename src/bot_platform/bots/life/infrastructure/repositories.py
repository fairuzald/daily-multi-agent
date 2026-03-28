from __future__ import annotations

from datetime import datetime

from bot_platform.bots.life.domain.models import LifeItem, LifeItemStatus, LifeItemType
from bot_platform.shared.persistence.json_store import JsonKeyValueStore


class LifeRepository:
    ITEMS_KEY = "life:items"

    def __init__(self, database_url: str) -> None:
        self.store = JsonKeyValueStore(database_url)

    def save(self, item: LifeItem) -> LifeItem:
        items = self._load_items()
        items = [existing for existing in items if existing.item_id != item.item_id]
        items.append(item)
        items.sort(key=lambda value: value.created_at)
        self._persist_items(items)
        return item

    def get(self, item_id: str) -> LifeItem | None:
        for item in self._load_items():
            if item.item_id == item_id:
                return item
        return None

    def list_all(self) -> list[LifeItem]:
        return self._load_items()

    def list_by_type(self, item_type: LifeItemType) -> list[LifeItem]:
        return [item for item in self._load_items() if item.type == item_type]

    def list_due_for_reminder(self, now: datetime) -> list[LifeItem]:
        due_items: list[LifeItem] = []
        for item in self._load_items():
            trigger = item.remind_at or item.due_at
            if trigger is None:
                continue
            if item.status not in {LifeItemStatus.OPEN, LifeItemStatus.SNOOZED}:
                continue
            if trigger > now:
                continue
            if item.last_reminded_at is not None and item.last_reminded_at >= trigger:
                continue
            due_items.append(item)
        due_items.sort(key=lambda item: item.scheduled_at() or item.created_at)
        return due_items

    def _load_items(self) -> list[LifeItem]:
        payload = self.store.get_value(self.ITEMS_KEY) or []
        return [LifeItem.model_validate(item) for item in payload]

    def _persist_items(self, items: list[LifeItem]) -> None:
        self.store.set_value(self.ITEMS_KEY, [item.model_dump(mode="json") for item in items])
