from __future__ import annotations

from dataclasses import dataclass

from bot_platform.bots.finance.models import InputMode, ParsedTransaction, TransactionRecord
from bot_platform.shared.persistence.json_store import JsonKeyValueStore


@dataclass
class PendingTransactionState:
    chat_id: int
    parsed: ParsedTransaction
    input_mode: InputMode = InputMode.TEXT


@dataclass
class ReplyMessageContext:
    kind: str
    transaction_id: str = ""
    month: str = ""


class BotStateStore:
    def __init__(self, database_url: str) -> None:
        self.store = JsonKeyValueStore(database_url)
        self._pending: dict[int, PendingTransactionState] = {}
        self._last_transaction_ids: dict[int, str] = {}
        self._reply_contexts: dict[int, ReplyMessageContext] = {}
        self._transaction_snapshots: dict[str, TransactionRecord] = {}
        self._setup_modes: dict[int, str] = {}

    @staticmethod
    def _pending_key(chat_id: int) -> str:
        return f"pending:{chat_id}"

    @staticmethod
    def _last_transaction_key(chat_id: int) -> str:
        return f"last_transaction:{chat_id}"

    @staticmethod
    def _reply_context_key(chat_id: int, message_id: int) -> str:
        return f"reply_context:{chat_id}:{message_id}"

    @staticmethod
    def _transaction_snapshot_key(transaction_id: str) -> str:
        return f"transaction_snapshot:{transaction_id}"

    @staticmethod
    def _setup_mode_key(chat_id: int) -> str:
        return f"setup_mode:{chat_id}"

    def get_owner_user_id(self) -> int | None:
        value = self.store.get_value("owner_user_id")
        return int(value) if value is not None else None

    def set_owner_user_id(self, user_id: int) -> None:
        self.store.set_value("owner_user_id", user_id)

    def get_active_sheet_id(self) -> str:
        value = self.store.get_value("active_sheet_id")
        return str(value or "")

    def set_active_sheet_id(self, sheet_id: str) -> None:
        self.store.set_value("active_sheet_id", sheet_id)

    def is_awaiting_sheet_link(self) -> bool:
        value = self.store.get_value("awaiting_sheet_link")
        return bool(value) if value is not None else False

    def set_awaiting_sheet_link(self, awaiting: bool) -> None:
        self.store.set_value("awaiting_sheet_link", awaiting)

    def set_pending(self, chat_id: int, parsed: ParsedTransaction, input_mode: InputMode = InputMode.TEXT) -> None:
        state = PendingTransactionState(chat_id=chat_id, parsed=parsed, input_mode=input_mode)
        self._pending[chat_id] = state
        self.store.set_value(
            self._pending_key(chat_id),
            {
                "chat_id": chat_id,
                "parsed": parsed.model_dump(mode="json"),
                "input_mode": input_mode.value,
            },
        )

    def get_pending(self, chat_id: int) -> PendingTransactionState | None:
        pending = self._pending.get(chat_id)
        if pending is not None:
            return pending
        value = self.store.get_value(self._pending_key(chat_id))
        if value is None:
            return None
        pending = PendingTransactionState(
            chat_id=int(value["chat_id"]),
            parsed=ParsedTransaction.model_validate(value["parsed"]),
            input_mode=InputMode(value["input_mode"]),
        )
        self._pending[chat_id] = pending
        return pending

    def clear_pending(self, chat_id: int) -> None:
        self._pending.pop(chat_id, None)
        self.store.delete_value(self._pending_key(chat_id))

    def set_last_transaction_id(self, chat_id: int, transaction_id: str) -> None:
        self._last_transaction_ids[chat_id] = transaction_id
        self.store.set_value(self._last_transaction_key(chat_id), transaction_id)

    def get_last_transaction_id(self, chat_id: int) -> str | None:
        transaction_id = self._last_transaction_ids.get(chat_id)
        if transaction_id is not None:
            return transaction_id
        value = self.store.get_value(self._last_transaction_key(chat_id))
        if value is None:
            return None
        transaction_id = str(value)
        self._last_transaction_ids[chat_id] = transaction_id
        return transaction_id

    def set_reply_context(self, chat_id: int, message_id: int, context: ReplyMessageContext) -> None:
        key = (chat_id, message_id)
        self._reply_contexts[key] = context
        self.store.set_value(
            self._reply_context_key(chat_id, message_id),
            {
                "kind": context.kind,
                "transaction_id": context.transaction_id,
                "month": context.month,
            },
        )

    def get_reply_context(self, chat_id: int, message_id: int | None) -> ReplyMessageContext | None:
        if message_id is None:
            return None
        key = (chat_id, message_id)
        context = self._reply_contexts.get(key)
        if context is not None:
            return context
        value = self.store.get_value(self._reply_context_key(chat_id, message_id))
        if value is None:
            return None
        context = ReplyMessageContext(
            kind=str(value.get("kind") or ""),
            transaction_id=str(value.get("transaction_id") or ""),
            month=str(value.get("month") or ""),
        )
        self._reply_contexts[key] = context
        return context

    def set_transaction_snapshot(self, transaction: TransactionRecord) -> None:
        self._transaction_snapshots[transaction.transaction_id] = transaction
        self.store.set_value(self._transaction_snapshot_key(transaction.transaction_id), transaction.model_dump(mode="json"))

    def get_transaction_snapshot(self, transaction_id: str) -> TransactionRecord | None:
        snapshot = self._transaction_snapshots.get(transaction_id)
        if snapshot is not None:
            return snapshot
        value = self.store.get_value(self._transaction_snapshot_key(transaction_id))
        if value is None:
            return None
        snapshot = TransactionRecord.model_validate(value)
        self._transaction_snapshots[transaction_id] = snapshot
        return snapshot

    def set_setup_mode(self, chat_id: int, mode: str) -> None:
        self._setup_modes[chat_id] = mode
        self.store.set_value(self._setup_mode_key(chat_id), mode)

    def get_setup_mode(self, chat_id: int) -> str:
        mode = self._setup_modes.get(chat_id)
        if mode is not None:
            return mode
        value = self.store.get_value(self._setup_mode_key(chat_id))
        if value is None:
            return ""
        mode = str(value)
        self._setup_modes[chat_id] = mode
        return mode

    def clear_setup_mode(self, chat_id: int) -> None:
        self._setup_modes.pop(chat_id, None)
        self.store.delete_value(self._setup_mode_key(chat_id))
