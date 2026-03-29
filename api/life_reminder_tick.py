from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bot_platform.shared.bootstrap.factory import create_life_application_components
from bot_platform.shared.config.settings import Settings
from bot_platform.shared.fastapi import RateLimitMiddleware, RateLimitRule
from bot_platform.shared.logging.setup import configure_logging

configure_logging()
app = FastAPI()
_rate_limit_settings = Settings.from_env()
app.add_middleware(
    RateLimitMiddleware,
    window_seconds=_rate_limit_settings.rate_limit_window_seconds,
    trust_forwarded_for=_rate_limit_settings.rate_limit_trust_forwarded_for,
    rules=(
        RateLimitRule(
            path="/api/life_reminder_tick",
            max_requests=_rate_limit_settings.rate_limit_reminder_max_requests_per_ip,
        ),
    ),
)


async def _dispatch_due_reminders() -> int:
    settings = Settings.from_env()
    application, service = create_life_application_components(settings)
    await application.initialize()
    try:
        return await service.dispatch_due_reminders(bot=application.bot)
    finally:
        await application.shutdown()


@app.post("/api/life_reminder_tick")
async def life_reminder_tick(x_reminder_token: str | None = Header(default=None)) -> JSONResponse:
    settings = Settings.from_env()
    if settings.life_reminder_tick_token and x_reminder_token != settings.life_reminder_tick_token:
        raise HTTPException(status_code=401, detail="Unauthorized reminder tick")
    sent = await _dispatch_due_reminders()
    return JSONResponse({"sent": sent})
