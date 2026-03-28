from __future__ import annotations

from typing import Any

from bot_platform.shared.persistence.json_store import JsonKeyValueStore


class NamespacedStateStore:
    def __init__(self, database_url: str, *, namespace: str) -> None:
        self.namespace = namespace
        self.store = JsonKeyValueStore(database_url)

    def claim_processed_update(self, update_id: int) -> bool:
        return self.store.claim_value(self._processed_update_key(update_id), {"update_id": update_id})

    def release_processed_update(self, update_id: int) -> None:
        self.store.delete_value(self._processed_update_key(update_id))

    def get_owner_user_id(self) -> int | None:
        value = self.store.get_value(self._key("owner_user_id"))
        return int(value) if value is not None else None

    def set_owner_user_id(self, user_id: int) -> None:
        self.store.set_value(self._key("owner_user_id"), user_id)

    def get_owner_chat_id(self) -> int | None:
        value = self.store.get_value(self._key("owner_chat_id"))
        return int(value) if value is not None else None

    def set_owner_chat_id(self, chat_id: int) -> None:
        self.store.set_value(self._key("owner_chat_id"), chat_id)

    def set_reply_context_payload(self, chat_id: int, message_id: int, payload: dict[str, Any]) -> None:
        self.store.set_value(self._reply_context_key(chat_id, message_id), payload)

    def get_reply_context_payload(self, chat_id: int, message_id: int | None) -> dict[str, Any] | None:
        if message_id is None:
            return None
        value = self.store.get_value(self._reply_context_key(chat_id, message_id))
        return value if isinstance(value, dict) else None

    def set_pending_payload(self, chat_id: int, pending_name: str, payload: dict[str, Any]) -> None:
        self.store.set_value(self._pending_key(chat_id, pending_name), payload)

    def get_pending_payload(self, chat_id: int, pending_name: str) -> dict[str, Any] | None:
        value = self.store.get_value(self._pending_key(chat_id, pending_name))
        return value if isinstance(value, dict) else None

    def clear_pending_payload(self, chat_id: int, pending_name: str) -> None:
        self.store.delete_value(self._pending_key(chat_id, pending_name))

    def _key(self, suffix: str) -> str:
        return f"{self.namespace}:{suffix}"

    def _pending_key(self, chat_id: int, pending_name: str) -> str:
        return self._key(f"{pending_name}:{chat_id}")

    def _reply_context_key(self, chat_id: int, message_id: int) -> str:
        return self._key(f"reply_context:{chat_id}:{message_id}")

    def _processed_update_key(self, update_id: int) -> str:
        return self._key(f"processed_update:{update_id}")
