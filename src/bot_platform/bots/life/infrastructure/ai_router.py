from __future__ import annotations

from datetime import datetime
from typing import Callable

from bot_platform.bots.life.infrastructure.ai_client import LifeAIClient
from bot_platform.shared.ai.rotating_client import BaseRotatingAIClient


class RotatingLifeAIClient(BaseRotatingAIClient[LifeAIClient]):
    def __init__(
        self,
        primary: LifeAIClient,
        fallback: LifeAIClient | None = None,
        cooldown_seconds: int = 300,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(
            primary=primary,
            fallback=fallback,
            cooldown_seconds=cooldown_seconds,
            now_factory=now_factory,
        )

    def extract_life_items(self, raw_input: str, *, original_input: str = "", reference_time_iso: str, timezone_name: str):
        return self._run(
            lambda client: client.extract_life_items(
                raw_input,
                original_input=original_input,
                reference_time_iso=reference_time_iso,
                timezone_name=timezone_name,
            ),
            capability_name="extract_life_items",
        )

    def transcribe_voice_note(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        return self._run(
            lambda client: client.transcribe_voice_note(audio_bytes=audio_bytes, mime_type=mime_type),
            capability_name="transcribe_voice_note",
        )
