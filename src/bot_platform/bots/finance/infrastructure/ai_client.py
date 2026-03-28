from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bot_platform.bots.finance.domain.multi_transaction import MultiTransactionCandidate
from bot_platform.bots.finance.models import ParsedTransaction, TransactionRecord


@dataclass(frozen=True)
class AIProviderExhaustion:
    retry_after_seconds: int | None = None


class AIClient(Protocol):
    def parse_transaction(self, raw_input: str) -> ParsedTransaction: ...

    def extract_multi_transaction(self, raw_input: str) -> MultiTransactionCandidate | None: ...

    def parse_transaction_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        caption: str = "",
    ) -> ParsedTransaction: ...

    def correct_transaction(self, original: TransactionRecord, correction_input: str) -> ParsedTransaction: ...

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
