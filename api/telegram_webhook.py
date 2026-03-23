from __future__ import annotations
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

# Vercel's Python runtime does not automatically add our Poetry `src/` layout
# to sys.path, so bootstrap it before importing the app package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bot_finance_telegram.app import (
    _humanize_processing_error,
    add_categories_command,
    add_payment_method_command,
    application_error_handler,
    help_command,
    month_command,
    photo_message,
    set_sheet_command,
    start_command,
    status_command,
    today_command,
    text_message,
    voice_message,
    week_command,
    whoami_command,
)
from bot_finance_telegram.config import Settings
from bot_finance_telegram.runtime import create_telegram_application, process_webhook_update


async def _process_payload(payload: dict[str, Any]) -> None:
    settings = Settings.from_env()
    application = create_telegram_application(
        settings,
        start_command=start_command,
        help_command=help_command,
        status_command=status_command,
        whoami_command=whoami_command,
        set_sheet_command=set_sheet_command,
        add_payment_method_command=add_payment_method_command,
        add_categories_command=add_categories_command,
        today_command=today_command,
        week_command=week_command,
        month_command=month_command,
        voice_message=voice_message,
        photo_message=photo_message,
        text_message=text_message,
        application_error_handler=application_error_handler,
    )
    await process_webhook_update(application, payload)


app = FastAPI()


@app.post("/api/telegram_webhook", response_class=PlainTextResponse)
async def telegram_webhook(request: Request) -> str:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Webhook payload must be a JSON object")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc

    try:
        await _process_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        humanized = _humanize_processing_error(exc, source="webhook request")
        raise HTTPException(status_code=500, detail=str(humanized)) from exc

    return "OK"
