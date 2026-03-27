import importlib
import sys
import asyncio

from bot_platform.shared.bootstrap.factory import create_telegram_application
from bot_platform.shared.config.settings import Settings


async def _noop(*args, **kwargs):
    return None


def _settings() -> Settings:
    return Settings(
        telegram_bot_token="token",
        gemini_api_key="gemini",
        database_url="postgresql://example",
        google_service_account_json='{"type":"service_account","client_email":"service@example.com"}',
    )


def test_create_telegram_application_attaches_bot_handlers() -> None:
    import bot_platform.shared.bootstrap.factory as factory

    class FakeController:
        async def start_command(self, *args, **kwargs): return None
        async def help_command(self, *args, **kwargs): return None
        async def status_command(self, *args, **kwargs): return None
        async def whoami_command(self, *args, **kwargs): return None
        async def set_sheet_command(self, *args, **kwargs): return None
        async def add_payment_method_command(self, *args, **kwargs): return None
        async def add_categories_command(self, *args, **kwargs): return None
        async def today_command(self, *args, **kwargs): return None
        async def week_command(self, *args, **kwargs): return None
        async def month_command(self, *args, **kwargs): return None
        async def delete_last_command(self, *args, **kwargs): return None
        async def delete_reply_command(self, *args, **kwargs): return None
        async def edit_last_command(self, *args, **kwargs): return None
        async def edit_reply_command(self, *args, **kwargs): return None
        async def read_command(self, *args, **kwargs): return None
        async def budget_set_command(self, *args, **kwargs): return None
        async def budget_show_command(self, *args, **kwargs): return None
        async def compare_month_command(self, *args, **kwargs): return None
        async def voice_message(self, *args, **kwargs): return None
        async def photo_message(self, *args, **kwargs): return None
        async def text_message(self, *args, **kwargs): return None
        async def application_error_handler(self, *args, **kwargs): return None

    original_create_components = factory.create_application_components
    factory.create_application_components = lambda settings: (object(), FakeController())  # type: ignore[assignment]
    application = create_telegram_application(_settings())
    factory.create_application_components = original_create_components

    assert "bot_handlers" in application.bot_data


def test_vercel_webhook_requires_post() -> None:
    from api.telegram_webhook import app

    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/telegram_webhook")

    assert "POST" in route.methods
    assert "GET" not in route.methods


def test_vercel_webhook_processes_valid_post(monkeypatch) -> None:
    from api import telegram_webhook
    from api.telegram_webhook import telegram_webhook as endpoint

    calls: list[dict] = []
    
    async def fake_process_payload(payload: dict) -> None:
        calls.append(payload)
    
    monkeypatch.setattr(telegram_webhook, "_process_payload", fake_process_payload)

    class FakeRequest:
        async def json(self) -> dict:
            return {"update_id": 123}

    response = asyncio.run(endpoint(FakeRequest()))

    assert response == "OK"
    assert calls == [{"update_id": 123}]


def test_vercel_webhook_module_bootstraps_src_path(monkeypatch) -> None:
    original_sys_path = list(sys.path)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if not p.endswith("/src")], raising=False)
    sys.modules.pop("api.telegram_webhook", None)

    module = importlib.import_module("api.telegram_webhook")

    assert module.SRC_DIR.as_posix().endswith("/src")
    assert str(module.SRC_DIR) in sys.path

    monkeypatch.setattr(sys, "path", original_sys_path, raising=False)
