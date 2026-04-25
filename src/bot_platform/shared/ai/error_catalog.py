from __future__ import annotations

STRUCTURED_OUTPUT_ERROR_TOKENS = (
    "invalid intent payload",
    "invalid transaction payload",
    "invalid image transaction payload",
    "invalid corrected transaction payload",
    "invalid life item payload",
    "not valid json",
    "empty response",
    "empty transcription",
    "raw_input cannot be empty",
    "audio payload is empty",
    "image payload is empty",
    "correction input cannot be empty",
    "voice note support is not configured",
    "image parsing is not configured",
)

PROVIDER_PASSTHROUGH_ERROR_TOKENS = (
    "openrouter error",
    "openrouter failed",
    "gemini",
    "generativelanguage.googleapis.com",
    "upstream",
    "api error",
    "payment required",
    "not found",
    "not configured for the life bot",
    "not configured for the finance bot",
)

GEMINI_PROVIDER_TOKENS = (
    "gemini",
    "generativelanguage.googleapis.com",
    "resource_exhausted",
    "quota exceeded",
)

FALLBACK_ELIGIBLE_ERROR_TOKENS = (
    "invalid intent payload",
    "empty response",
    "empty transcription",
    "not valid json",
    "invalid transaction payload",
    "invalid image transaction payload",
    "invalid corrected transaction payload",
    "invalid life item payload",
    "unsupported",
    "not configured",
    "openrouter failed",
    "openrouter error",
    "gemini returned invalid",
)
