from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.ext import Application


async def process_webhook_update(application: Application, payload: dict[str, Any]) -> None:
    update_id = payload.get("update_id")
    bot_service = application.bot_data.get("bot_handlers")
    claimed = False
    if isinstance(update_id, int) and bot_service is not None:
        claimed = bot_service.state_store.claim_processed_update(update_id)
        if not claimed:
            return

    await application.initialize()
    try:
        update = Update.de_json(payload, application.bot)
        await application.process_update(update)
    except Exception:
        if claimed and isinstance(update_id, int) and bot_service is not None:
            bot_service.state_store.release_processed_update(update_id)
        raise
    finally:
        await application.shutdown()
