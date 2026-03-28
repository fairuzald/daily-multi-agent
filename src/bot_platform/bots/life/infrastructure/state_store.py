from __future__ import annotations

from dataclasses import dataclass

from bot_platform.shared.persistence.namespaced_state import NamespacedStateStore


@dataclass
class LifeReplyContext:
    kind: str = "item"
    item_id: str = ""


@dataclass
class PendingLifeParseState:
    raw_input: str


class LifeStateStore:
    def __init__(self, database_url: str) -> None:
        self.shared = NamespacedStateStore(database_url, namespace="life")

    def get_owner_user_id(self) -> int | None:
        return self.shared.get_owner_user_id()

    def set_owner_user_id(self, user_id: int) -> None:
        self.shared.set_owner_user_id(user_id)

    def get_owner_chat_id(self) -> int | None:
        return self.shared.get_owner_chat_id()

    def set_owner_chat_id(self, chat_id: int) -> None:
        self.shared.set_owner_chat_id(chat_id)

    def claim_processed_update(self, update_id: int) -> bool:
        return self.shared.claim_processed_update(update_id)

    def release_processed_update(self, update_id: int) -> None:
        self.shared.release_processed_update(update_id)

    def set_reply_context(self, chat_id: int, message_id: int, context: LifeReplyContext) -> None:
        self.shared.set_reply_context_payload(
            chat_id,
            message_id,
            {
                "kind": context.kind,
                "item_id": context.item_id,
            },
        )

    def get_reply_context(self, chat_id: int, message_id: int | None) -> LifeReplyContext | None:
        value = self.shared.get_reply_context_payload(chat_id, message_id)
        if not isinstance(value, dict):
            return None
        kind = str(value.get("kind") or "item")
        item_id = str(value.get("item_id") or "")
        if kind == "item" and not item_id:
            return None
        return LifeReplyContext(kind=kind, item_id=item_id)

    def set_pending_parse(self, chat_id: int, pending: PendingLifeParseState) -> None:
        self.shared.set_pending_payload(chat_id, "pending_parse", {"raw_input": pending.raw_input})

    def get_pending_parse(self, chat_id: int) -> PendingLifeParseState | None:
        value = self.shared.get_pending_payload(chat_id, "pending_parse")
        if not isinstance(value, dict) or not str(value.get("raw_input") or "").strip():
            return None
        return PendingLifeParseState(raw_input=str(value["raw_input"]))

    def clear_pending_parse(self, chat_id: int) -> None:
        self.shared.clear_pending_payload(chat_id, "pending_parse")
