from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AIProviderExhaustion:
    retry_after_seconds: int | None = None


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
    retry_match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", error_text, flags=re.IGNORECASE)
    if retry_match:
        return int(float(retry_match.group(1)))
    return None
