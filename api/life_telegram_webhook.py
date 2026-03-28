from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bot_platform.shared.bootstrap.factory import create_life_telegram_application
from bot_platform.shared.config.settings import Settings
from bot_platform.shared.logging.setup import configure_logging
from bot_platform.shared.telegram.runtime import process_webhook_update

configure_logging()


async def _process_payload(payload: dict[str, Any]) -> None:
    settings = Settings.from_env()
    application = create_life_telegram_application(settings)
    await process_webhook_update(application, payload)


app = FastAPI()


@app.post("/api/life_telegram_webhook", response_class=PlainTextResponse)
async def life_telegram_webhook(request: Request) -> str:
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
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return "OK"
