from __future__ import annotations

from typing import Protocol

from bot_platform.bots.life.domain.models import ParsedLifeBatch


class LifeAIClient(Protocol):
    def extract_life_items(
        self,
        raw_input: str,
        *,
        original_input: str = "",
        reference_time_iso: str,
        timezone_name: str,
    ) -> ParsedLifeBatch: ...

    def transcribe_voice_note(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str: ...
