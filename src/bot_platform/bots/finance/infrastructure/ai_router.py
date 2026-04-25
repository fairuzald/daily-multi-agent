from __future__ import annotations

from datetime import datetime
from typing import Callable

from bot_platform.bots.finance.domain.extraction import FinanceMessageExtraction
from bot_platform.bots.finance.infrastructure.ai_client import AIClient
from bot_platform.shared.ai.rotating_client import BaseRotatingAIClient


class RotatingAIClient(BaseRotatingAIClient[AIClient]):
    def __init__(
        self,
        primary: AIClient,
        fallback: AIClient | None = None,
        cooldown_seconds: int = 300,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(
            primary=primary,
            fallback=fallback,
            cooldown_seconds=cooldown_seconds,
            now_factory=now_factory,
        )

    def extract_message(
        self,
        raw_input: str,
        *,
        reply_context_kind: str = "",
        reply_context_text: str = "",
        pending_kind: str = "",
        message_datetime_iso: str = "",
        image_bytes: bytes | None = None,
        mime_type: str = "image/jpeg",
        caption: str = "",
        original=None,
    ) -> FinanceMessageExtraction:
        return self._run(
            lambda client: client.extract_message(
                raw_input,
                reply_context_kind=reply_context_kind,
                reply_context_text=reply_context_text,
                pending_kind=pending_kind,
                message_datetime_iso=message_datetime_iso,
                image_bytes=image_bytes,
                mime_type=mime_type,
                caption=caption,
                original=original,
            )
        )

    def parse_transaction(self, raw_input: str):
        return self._run(lambda client: client.parse_transaction(raw_input))

    def extract_multi_transaction(self, raw_input: str):
        return self._run(lambda client: client.extract_multi_transaction(raw_input))

    def parse_transaction_image(self, image_bytes: bytes, mime_type: str = "image/jpeg", caption: str = ""):
        return self._run(lambda client: client.parse_transaction_image(image_bytes=image_bytes, mime_type=mime_type, caption=caption))

    def correct_transaction(self, original, correction_input: str):
        return self._run(lambda client: client.correct_transaction(original=original, correction_input=correction_input))

    def transcribe_voice_note(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        return self._run(lambda client: client.transcribe_voice_note(audio_bytes=audio_bytes, mime_type=mime_type))
