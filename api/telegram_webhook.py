from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

# Vercel's Python runtime does not automatically add our Poetry `src/` layout
# to sys.path, so bootstrap it before importing the app package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bot_platform.shared.bootstrap.factory import create_life_application_components, create_life_telegram_application, create_telegram_application
from bot_platform.shared.config.settings import Settings
from bot_platform.shared.fastapi import RateLimitMiddleware, RateLimitRule
from bot_platform.shared.logging.setup import configure_logging
from bot_platform.bots.finance.interfaces.telegram.controller import (
    humanize_processing_error,
)
from bot_platform.shared.telegram.runtime import process_webhook_update

configure_logging()
logger = logging.getLogger(__name__)


async def _process_payload(payload: dict[str, Any]) -> None:
    settings = Settings.from_env()
    application = create_telegram_application(settings)
    await process_webhook_update(application, payload)


async def _process_life_payload(payload: dict[str, Any]) -> None:
    settings = Settings.from_env()
    application = create_life_telegram_application(settings)
    await process_webhook_update(application, payload)


async def _dispatch_life_reminders() -> int:
    settings = Settings.from_env()
    application, service = create_life_application_components(settings)
    await application.initialize()
    try:
        return await service.dispatch_due_reminders(bot=application.bot)
    finally:
        await application.shutdown()


app = FastAPI()
_rate_limit_settings = Settings.from_env()
app.add_middleware(
    RateLimitMiddleware,
    window_seconds=_rate_limit_settings.rate_limit_window_seconds,
    trust_forwarded_for=_rate_limit_settings.rate_limit_trust_forwarded_for,
    rules=(
        RateLimitRule(
            path="/api/telegram_webhook",
            max_requests=_rate_limit_settings.rate_limit_webhook_max_requests_per_ip,
        ),
        RateLimitRule(
            path="/api/life_telegram_webhook",
            max_requests=_rate_limit_settings.rate_limit_webhook_max_requests_per_ip,
        ),
        RateLimitRule(
            path="/api/life_reminder_tick",
            max_requests=_rate_limit_settings.rate_limit_reminder_max_requests_per_ip,
        ),
    ),
)


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
        logger.exception("Finance webhook rejected payload with value error")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Finance webhook processing failed", extra={"update_id": payload.get("update_id")})
        humanized = humanize_processing_error(exc, source="webhook request")
        raise HTTPException(status_code=500, detail=str(humanized)) from exc

    return "OK"


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
        await _process_life_payload(payload)
    except ValueError as exc:
        logger.exception("Life webhook rejected payload with value error")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        logger.exception("Life webhook rejected payload with permission error")
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Life webhook processing failed", extra={"update_id": payload.get("update_id")})
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return "OK"


@app.post("/api/life_reminder_tick")
async def life_reminder_tick(x_reminder_token: str | None = Header(default=None)) -> JSONResponse:
    settings = Settings.from_env()
    if settings.life_reminder_tick_token and x_reminder_token != settings.life_reminder_tick_token:
        raise HTTPException(status_code=401, detail="Unauthorized reminder tick")
    sent = await _dispatch_life_reminders()
    return JSONResponse({"sent": sent})
