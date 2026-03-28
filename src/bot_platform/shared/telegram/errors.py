from __future__ import annotations

import re

import httpx


def humanize_processing_error_text(exc: Exception, *, source: str) -> str:
    error_text = str(exc)

    if isinstance(exc, PermissionError):
        return error_text

    if (
        "RESOURCE_EXHAUSTED" in error_text
        or "quota exceeded" in error_text.lower()
        or "429" in error_text
        or "temporarily exhausted" in error_text.lower()
    ):
        retry_match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", error_text, flags=re.IGNORECASE)
        retry_seconds = ""
        if retry_match:
            retry_seconds = str(int(float(retry_match.group(1))))
        if retry_seconds:
            return f"The AI service is temporarily exhausted. Please wait about {retry_seconds} seconds and try again."
        return "The AI service is temporarily exhausted. Please wait a bit and try again."

    if "deadline" in error_text.lower() or "timeout" in error_text.lower():
        return f"The {source} took too long to process. Please try again with a shorter {source} or simpler input."

    if "permission" in error_text.lower() or "forbidden" in error_text.lower():
        return "The bot could not access the AI service for that request. Please check the API key or try again later."

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        body = (exc.response.text or "").strip()
        return f"HTTP error {status}: {body or error_text}"

    if any(token in error_text.lower() for token in ("openrouter error", "gemini", "upstream", "api error", "payment required", "not found")):
        return error_text

    return f"I couldn't process that {source} safely right now. Please try again or send a simpler version."
