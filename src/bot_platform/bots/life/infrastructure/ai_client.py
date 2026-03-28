from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bot_platform.bots.life.domain.models import ParsedLifeBatch


@dataclass(frozen=True)
class AIProviderExhaustion:
    retry_after_seconds: int | None = None


class LifeAIClient(Protocol):
    def parse_life_items(self, raw_input: str, *, reference_time_iso: str, timezone_name: str) -> ParsedLifeBatch: ...

    def correct_life_items(
        self,
        *,
        original_input: str,
        correction_input: str,
        reference_time_iso: str,
        timezone_name: str,
    ) -> ParsedLifeBatch: ...

    def transcribe_voice_note(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str: ...


def detect_provider_exhaustion(exc: Exception) -> AIProviderExhaustion | None:
    text = str(exc).lower()
    if not any(
        marker in text
        for marker in (
            "resource_exhausted",
            "quota",
            "rate limit",
            "too many requests",
            "429",
            "402",
            "payment required",
            "requires at least $",
            "insufficient balance",
            "credit balance",
        )
    ):
        return None
    retry_after = _extract_retry_after_seconds(str(exc))
    return AIProviderExhaustion(retry_after_seconds=retry_after)


def _extract_retry_after_seconds(error_text: str) -> int | None:
    import re

    retry_match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", error_text, flags=re.IGNORECASE)
    if retry_match:
        return int(float(retry_match.group(1)))
    return None
