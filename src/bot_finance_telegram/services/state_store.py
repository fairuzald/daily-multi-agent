from __future__ import annotations

import json
from dataclasses import dataclass

from bot_finance_telegram.models import InputMode, ParsedTransaction, TransactionRecord


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
        self.database_url = database_url
        self._pending: dict[int, PendingTransactionState] = {}
        self._last_transaction_ids: dict[int, str] = {}
        self._reply_contexts: dict[int, ReplyMessageContext] = {}
        self._transaction_snapshots: dict[str, TransactionRecord] = {}
        self._setup_modes: dict[int, str] = {}
        self._ensure_schema()

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is not installed. Run `poetry install` first.") from exc
        return psycopg.connect(self.database_url)

    def _ensure_schema(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    state_key TEXT PRIMARY KEY,
                    state_value JSONB NOT NULL
                )
                """
            )
            conn.commit()

    def _get_value(self, key: str):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT state_value FROM bot_state WHERE state_key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else None

    def _set_value(self, key: str, value) -> None:
        payload = json.dumps(value)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bot_state (state_key, state_value)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (state_key)
                DO UPDATE SET state_value = EXCLUDED.state_value
                """,
                (key, payload),
            )
            conn.commit()

    def get_owner_user_id(self) -> int | None:
        value = self._get_value("owner_user_id")
        return int(value) if value is not None else None

    def set_owner_user_id(self, user_id: int) -> None:
        self._set_value("owner_user_id", user_id)

    def get_active_sheet_id(self) -> str:
        value = self._get_value("active_sheet_id")
        return str(value or "")

    def set_active_sheet_id(self, sheet_id: str) -> None:
        self._set_value("active_sheet_id", sheet_id)

    def is_awaiting_sheet_link(self) -> bool:
        value = self._get_value("awaiting_sheet_link")
        return bool(value) if value is not None else False

    def set_awaiting_sheet_link(self, awaiting: bool) -> None:
        self._set_value("awaiting_sheet_link", awaiting)

    def set_pending(self, chat_id: int, parsed: ParsedTransaction, input_mode: InputMode = InputMode.TEXT) -> None:
        self._pending[chat_id] = PendingTransactionState(chat_id=chat_id, parsed=parsed, input_mode=input_mode)

    def get_pending(self, chat_id: int) -> PendingTransactionState | None:
        return self._pending.get(chat_id)

    def clear_pending(self, chat_id: int) -> None:
        self._pending.pop(chat_id, None)

    def set_last_transaction_id(self, chat_id: int, transaction_id: str) -> None:
        self._last_transaction_ids[chat_id] = transaction_id

    def get_last_transaction_id(self, chat_id: int) -> str | None:
        return self._last_transaction_ids.get(chat_id)

    def set_reply_context(self, message_id: int, context: ReplyMessageContext) -> None:
        self._reply_contexts[message_id] = context

    def get_reply_context(self, message_id: int | None) -> ReplyMessageContext | None:
        if message_id is None:
            return None
        return self._reply_contexts.get(message_id)

    def set_transaction_snapshot(self, transaction: TransactionRecord) -> None:
        self._transaction_snapshots[transaction.transaction_id] = transaction

    def get_transaction_snapshot(self, transaction_id: str) -> TransactionRecord | None:
        return self._transaction_snapshots.get(transaction_id)

    def set_setup_mode(self, chat_id: int, mode: str) -> None:
        self._setup_modes[chat_id] = mode

    def get_setup_mode(self, chat_id: int) -> str:
        return self._setup_modes.get(chat_id, "")

    def clear_setup_mode(self, chat_id: int) -> None:
        self._setup_modes.pop(chat_id, None)
