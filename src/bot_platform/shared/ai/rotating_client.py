from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable, Generic, TypeVar

from bot_platform.shared.ai.error_catalog import FALLBACK_ELIGIBLE_ERROR_TOKENS
from bot_platform.shared.ai.provider_exhaustion import detect_provider_exhaustion

TClient = TypeVar("TClient")
TResult = TypeVar("TResult")


class BaseRotatingAIClient(Generic[TClient]):
    def __init__(
        self,
        *,
        primary: TClient,
        fallback: TClient | None = None,
        cooldown_seconds: int = 300,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.cooldown_seconds = cooldown_seconds
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self._primary_blocked_until: datetime | None = None

    def _run(
        self,
        operation: Callable[[TClient], TResult],
        *,
        capability_name: str | None = None,
    ) -> TResult:
        if self._should_skip_primary():
            return self._run_with_fallback(operation, capability_name=capability_name)

        try:
            result = operation(self.primary)
        except Exception as exc:
            exhaustion = detect_provider_exhaustion(exc)
            if exhaustion is None and not self._should_try_fallback(exc):
                raise
            if exhaustion is not None:
                self._block_primary(retry_after_seconds=exhaustion.retry_after_seconds)
            return self._run_with_fallback(operation, capability_name=capability_name, primary_exc=exc)

        self._primary_blocked_until = None
        return result

    def _run_with_fallback(
        self,
        operation: Callable[[TClient], TResult],
        *,
        capability_name: str | None = None,
        primary_exc: Exception | None = None,
    ) -> TResult:
        if self.fallback is None:
            raise primary_exc or RuntimeError("AI service is temporarily exhausted. Please try again later.")
        if not self._supports_capability(self.fallback, capability_name):
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
            raise

    @staticmethod
    def _supports_capability(client: TClient, capability_name: str | None) -> bool:
        if capability_name is None:
            return True
        capability = getattr(client, capability_name, None)
        return callable(capability)

    @staticmethod
    def _should_try_fallback(exc: Exception) -> bool:
        text = str(exc).lower()
        if not text:
            return False
        return any(token in text for token in FALLBACK_ELIGIBLE_ERROR_TOKENS)

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
