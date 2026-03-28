from __future__ import annotations

import re

import httpx


def humanize_processing_error_text(exc: Exception, *, source: str) -> str:
    error_text = str(exc)
    lowered = error_text.lower()

    if isinstance(exc, PermissionError):
        return error_text

    provider_message = _humanize_provider_error(error_text, lowered)
    if provider_message:
        return provider_message

    if "deadline" in lowered or "timeout" in lowered:
        return f"The {source} took too long to process. Please try again with a shorter {source} or simpler input."

    if "permission" in lowered or "forbidden" in lowered:
        return "The bot could not access the AI service for that request. Please check the API key or try again later."

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        body = (exc.response.text or "").strip()
        return f"HTTP error {status}: {body or error_text}"

    if any(
        token in lowered
        for token in (
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
    ):
        return error_text

    return f"I couldn't process that {source} safely right now. Please try again or send a simpler version."


def _humanize_provider_error(error_text: str, lowered: str) -> str | None:
    if "openrouter error" in lowered or "openrouter failed" in lowered:
        return error_text

    gemini_like = any(
        token in lowered
        for token in (
            "gemini",
            "generativelanguage.googleapis.com",
            "resource_exhausted",
            "quota exceeded",
        )
    )
    if gemini_like:
        retry_seconds = _extract_retry_seconds(error_text)
        model_match = re.search(r"model:\s*([a-zA-Z0-9._:-]+)", error_text, flags=re.IGNORECASE)
        model_suffix = f" for {model_match.group(1)}" if model_match else ""
        if retry_seconds:
            return f"Gemini error{model_suffix}: quota or rate limit exceeded. Retry in {retry_seconds}s."
        if "429" in error_text:
            return f"Gemini error{model_suffix}: quota or rate limit exceeded."
        return error_text

    if "temporarily exhausted" in lowered or "429" in error_text:
        retry_seconds = _extract_retry_seconds(error_text)
        if retry_seconds:
            return f"AI provider error: quota or rate limit exceeded. Retry in {retry_seconds}s."
        return "AI provider error: quota or rate limit exceeded."

    return None


def _extract_retry_seconds(error_text: str) -> str:
    retry_match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", error_text, flags=re.IGNORECASE)
    if not retry_match:
        return ""
    return str(int(float(retry_match.group(1))))
