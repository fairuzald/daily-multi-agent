from __future__ import annotations

import json
from typing import Any


class JsonKeyValueStore:
    def __init__(self, database_url: str, table_name: str = "bot_state") -> None:
        self.database_url = database_url
        self.table_name = table_name
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
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    state_key TEXT PRIMARY KEY,
                    state_value JSONB NOT NULL
                )
                """
            )
            conn.commit()

    def get_value(self, key: str) -> Any:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT state_value FROM {self.table_name} WHERE state_key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else None

    def set_value(self, key: str, value: Any) -> None:
        payload = json.dumps(value)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self.table_name} (state_key, state_value)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (state_key)
                DO UPDATE SET state_value = EXCLUDED.state_value
                """,
                (key, payload),
            )
            conn.commit()

    def delete_value(self, key: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"DELETE FROM {self.table_name} WHERE state_key = %s", (key,))
            conn.commit()
