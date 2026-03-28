from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable, TypeVar

from bot_platform.bots.finance.infrastructure.ai_client import AIClient, detect_provider_exhaustion

T = TypeVar("T")


class RotatingAIClient:
    def __init__(
        self,
        primary: AIClient,
        fallback: AIClient | None = None,
        cooldown_seconds: int = 300,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.cooldown_seconds = cooldown_seconds
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self._primary_blocked_until: datetime | None = None

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

    def _run(self, operation: Callable[[AIClient], T]) -> T:
        if self._should_skip_primary():
            return self._run_with_fallback(operation)

        try:
            result = operation(self.primary)
        except Exception as exc:
            exhaustion = detect_provider_exhaustion(exc)
            if exhaustion is None:
                raise
            self._block_primary(retry_after_seconds=exhaustion.retry_after_seconds)
            return self._run_with_fallback(operation, primary_exc=exc)

        self._primary_blocked_until = None
        return result

    def _run_with_fallback(self, operation: Callable[[AIClient], T], primary_exc: Exception | None = None) -> T:
        if self.fallback is None:
            raise primary_exc or RuntimeError("AI service is temporarily exhausted. Please try again later.")
        try:
            return operation(self.fallback)
        except Exception as fallback_exc:
            if detect_provider_exhaustion(fallback_exc) is not None:
                retry_seconds = self._retry_after_seconds()
                if retry_seconds:
                    raise RuntimeError(
                        f"429 RESOURCE_EXHAUSTED. AI providers are temporarily exhausted. Please retry in {retry_seconds}s."
                    ) from fallback_exc
                raise RuntimeError("429 RESOURCE_EXHAUSTED. AI providers are temporarily exhausted. Please try again soon.") from fallback_exc
            raise fallback_exc

    def _block_primary(self, retry_after_seconds: int | None) -> None:
        seconds = retry_after_seconds or self.cooldown_seconds
        self._primary_blocked_until = self._now_factory() + timedelta(seconds=seconds)

    def _should_skip_primary(self) -> bool:
        return self._primary_blocked_until is not None and self._now_factory() < self._primary_blocked_until

    def _retry_after_seconds(self) -> int | None:
        if self._primary_blocked_until is None:
            return None
        delta = self._primary_blocked_until - self._now_factory()
        if delta.total_seconds() <= 0:
            return None
        return int(delta.total_seconds())
