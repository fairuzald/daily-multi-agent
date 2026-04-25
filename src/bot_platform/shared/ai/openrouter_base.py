from __future__ import annotations

import httpx
import json
from typing import Any, Callable, TypeVar

from bot_platform.shared.ai.gemini_base import BaseGeminiClient

T = TypeVar("T")


class BaseOpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str,
        text_models: tuple[str, ...] = ("openrouter/free",),
        vision_models: tuple[str, ...] = ("openrouter/free",),
        audio_models: tuple[str, ...] = (),
        base_url: str = "https://openrouter.ai/api/v1",
        app_name: str = "bot-finance-telegram",
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.text_models = text_models
        self.vision_models = vision_models
        self.audio_models = audio_models
        self.base_url = base_url.rstrip("/")
        self.app_name = app_name
        self._http_client = http_client
        self._model_start_index = {"text": 0, "vision": 0, "audio": 0}

    def _chat_completion(self, *, model: str, messages: list[dict[str, Any]], response_format: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if response_format is not None:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://openrouter.ai/openrouter/free",
            "X-Title": self.app_name,
        }

        client = self._http_client or httpx.Client(timeout=60.0)
        should_close = self._http_client is None
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.is_error:
                raise RuntimeError(self._format_http_error(response))
            return response.json()
        finally:
            if should_close:
                client.close()

    def _call_json_model(
        self,
        *,
        capability: str,
        models: tuple[str, ...],
        messages: list[dict[str, Any]],
        empty_response_error: str,
        invalid_response_error: str,
        payload_normalizer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        def operation(model: str) -> dict[str, Any]:
            response = self._chat_completion(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            text = self._extract_message_text(response)
            if not text:
                raise ValueError(empty_response_error)
            try:
                payload = json.loads(BaseGeminiClient.extract_json_text(text))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{invalid_response_error}: {text}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{invalid_response_error}: expected a JSON object, got {type(payload).__name__}")
            if payload_normalizer is None:
                return payload
            return payload_normalizer(payload)

        return self._run_model_pool(capability, models, operation)

    def transcribe_voice_note(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        if not audio_bytes:
            raise ValueError("audio payload is empty")

        def operation(model: str) -> str:
            response = self._chat_completion(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": BaseGeminiClient.TRANSCRIBE_VOICE_NOTE_PROMPT,
                            },
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": self._base64_ascii(audio_bytes),
                                    "format": self._audio_format(mime_type),
                                },
                            },
                        ],
                    }
                ],
            )
            transcript = self._extract_message_text(response).strip()
            if not transcript:
                raise ValueError("OpenRouter returned an empty transcription")
            return transcript

        return self._run_model_pool("audio", self.audio_models, operation)

    @staticmethod
    def _format_http_error(response: httpx.Response) -> str:
        status = response.status_code
        detail = ""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                detail = str(
                    error_payload.get("message")
                    or error_payload.get("metadata")
                    or error_payload.get("code")
                    or ""
                ).strip()
            elif error_payload is not None:
                detail = str(error_payload).strip()
            if not detail:
                detail = str(payload.get("message") or "").strip()
        if not detail:
            detail = (response.text or "").strip()
        if detail:
            return f"OpenRouter error {status}: {detail}"
        return f"OpenRouter error {status}"

    def _run_model_pool(
        self,
        capability: str,
        models: tuple[str, ...],
        operation: Callable[[str], T],
    ) -> T:
        if not models:
            raise RuntimeError(f"OpenRouter {capability} models are not configured")

        errors: list[tuple[str, str]] = []
        start = self._model_start_index[capability] % len(models)
        for offset in range(len(models)):
            index = (start + offset) % len(models)
            model = models[index]
            try:
                result = operation(model)
            except Exception as exc:
                if not self._is_retryable_model_error(exc):
                    raise
                if len(models) == 1:
                    raise exc
                errors.append((model, str(exc)))
                continue
            self._model_start_index[capability] = (index + 1) % len(models)
            return result
        raise RuntimeError(self._format_model_pool_error(capability, errors))

    @staticmethod
    def _is_retryable_model_error(exc: Exception) -> bool:
        message = str(exc).lower()
        if isinstance(exc, RuntimeError):
            if any(code in message for code in ("401", "403", "invalid api key", "unauthorized", "forbidden")):
                return False
            return any(
                token in message
                for token in (
                    "400",
                    "402",
                    "404",
                    "408",
                    "409",
                    "422",
                    "429",
                    "500",
                    "502",
                    "503",
                    "504",
                    "payment required",
                    "not found",
                    "unsupported",
                    "rate limit",
                    "too many requests",
                    "temporarily",
                    "overloaded",
                    "timed out",
                    "timeout",
                )
            )
        if isinstance(exc, ValueError):
            return any(
                token in message
                for token in (
                    "empty response",
                    "empty transcription",
                    "not valid json",
                    "invalid transaction payload",
                    "invalid image transaction payload",
                    "invalid corrected transaction payload",
                    "invalid life item payload",
                )
            )
        return False

    @staticmethod
    def _format_model_pool_error(capability: str, errors: list[tuple[str, str]]) -> str:
        if not errors:
            return f"OpenRouter failed for {capability}"
        attempts = "; ".join(f"{model} ({detail})" for model, detail in errors)
        return f"OpenRouter failed for {capability}. Tried: {attempts}"

    @staticmethod
    def _extract_message_text(response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            return "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return str(content)

    @staticmethod
    def _audio_format(mime_type: str) -> str:
        if "/" not in mime_type:
            return "wav"
        subtype = mime_type.split("/", 1)[1].lower()
        if subtype == "mpeg":
            return "mp3"
        if subtype == "x-wav":
            return "wav"
        return subtype

    @staticmethod
    def _base64_ascii(payload: bytes) -> str:
        import base64

        return base64.b64encode(payload).decode("ascii")
