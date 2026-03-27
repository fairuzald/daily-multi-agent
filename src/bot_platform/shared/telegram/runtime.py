from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.ext import Application


async def process_webhook_update(application: Application, payload: dict[str, Any]) -> None:
    await application.initialize()
    try:
        update = Update.de_json(payload, application.bot)
        await application.process_update(update)
    finally:
        await application.shutdown()
