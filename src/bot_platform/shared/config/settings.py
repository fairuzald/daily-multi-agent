from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def load_local_env() -> None:
    project_root = Path(__file__).resolve().parents[4]
    load_dotenv(project_root / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    gemini_api_key: str
    primary_ai_provider: str = "gemini"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_models_text: tuple[str, ...] = ("openrouter/free",)
    openrouter_models_vision: tuple[str, ...] = ("openrouter/free",)
    openrouter_models_audio: tuple[str, ...] = ()
    ai_fallback_cooldown_seconds: int = 300
    google_sheet_id: str = ""
    google_service_account_json: str = ""
    database_url: str = ""
    default_currency: str = "IDR"
    default_timezone: str = "Asia/Jakarta"
    low_confidence_threshold: float = 0.8

    @classmethod
    def from_env(cls) -> "Settings":
        load_local_env()
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            primary_ai_provider=os.getenv("PRIMARY_AI_PROVIDER", "gemini").strip().lower(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            openrouter_models_text=_env_model_list("OPENROUTER_MODELS_TEXT", default=("openrouter/free",)),
            openrouter_models_vision=_env_model_list("OPENROUTER_MODELS_VISION", default=("openrouter/free",)),
            openrouter_models_audio=_env_model_list("OPENROUTER_MODELS_AUDIO"),
            ai_fallback_cooldown_seconds=int(os.getenv("AI_FALLBACK_COOLDOWN_SECONDS", "300")),
            google_sheet_id=os.getenv("GOOGLE_SHEET_ID", ""),
            google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
            database_url=os.getenv("DATABASE_URL", ""),
            default_currency=os.getenv("DEFAULT_CURRENCY", "IDR"),
            default_timezone=os.getenv("DEFAULT_TIMEZONE", "Asia/Jakarta"),
            low_confidence_threshold=float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.8")),
        )

    def validate_required(self) -> list[str]:
        missing: list[str] = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if self.primary_ai_provider not in {"gemini", "openrouter"}:
            missing.append("PRIMARY_AI_PROVIDER")
        elif self.primary_ai_provider == "gemini" and not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        elif self.primary_ai_provider == "openrouter" and not self.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY")
        if self.openrouter_api_key:
            if not self.openrouter_models_text:
                missing.append("OPENROUTER_MODELS_TEXT")
            if not self.openrouter_models_vision:
                missing.append("OPENROUTER_MODELS_VISION")
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not self.google_service_account_json:
            missing.append("GOOGLE_SERVICE_ACCOUNT_JSON")
        return missing

    def validate_google_required(self) -> list[str]:
        missing: list[str] = []
        if not self.google_sheet_id:
            missing.append("GOOGLE_SHEET_ID")
        if not self.google_service_account_json:
            missing.append("GOOGLE_SERVICE_ACCOUNT_JSON")
        return missing

    def service_account_email(self) -> str:
        import json

        payload = json.loads(self.google_service_account_json)
        return str(payload.get("client_email") or "")


def _env_model_list(name: str, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    return values or default
