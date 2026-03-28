from __future__ import annotations

import base64
import json
from typing import Any

import httpx
from pydantic import ValidationError

from bot_platform.bots.finance.domain.multi_transaction import build_ai_multi_transaction_candidate
from bot_platform.bots.finance.infrastructure.gemini_gateway import GeminiClient
from bot_platform.bots.finance.models import ParsedTransaction, TransactionRecord


class OpenRouterClient:
    def __init__(
        self,
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
        self._transaction_prompt = GeminiClient._load_prompt("transaction_parser.txt")
        self._multi_transaction_prompt = GeminiClient._load_prompt("multi_transaction_parser.txt")
        self._image_prompt = GeminiClient._load_prompt("receipt_image_parser.txt")
        self._correction_prompt = GeminiClient._load_prompt("transaction_correction_parser.txt")
        self._model_start_index = {"text": 0, "vision": 0, "audio": 0}

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
                                "text": (
                                    "Transcribe this Indonesian Telegram voice note. "
                                    "Return only the spoken transcript text without Markdown or explanation."
                                ),
                            },
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": base64.b64encode(audio_bytes).decode("ascii"),
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

    def parse_transaction(self, raw_input: str) -> ParsedTransaction:
        if not raw_input.strip():
            raise ValueError("raw_input cannot be empty")
        payload = self._call_json_model(
            capability="text",
            models=self.text_models,
            messages=[{"role": "user", "content": f"{self._transaction_prompt}\n\nUser input:\n{raw_input}"}],
            empty_response_error="OpenRouter returned an empty response",
            invalid_response_error="OpenRouter response was not valid JSON",
        )
        try:
            return ParsedTransaction.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"OpenRouter returned invalid transaction payload: {exc}") from exc

    def extract_multi_transaction(self, raw_input: str):
        if not raw_input.strip():
            raise ValueError("raw_input cannot be empty")
        payload = self._call_json_model(
            capability="text",
            models=self.text_models,
            messages=[{"role": "user", "content": f"{self._multi_transaction_prompt}\n\nUser input:\n{raw_input}"}],
            empty_response_error="OpenRouter returned an empty response for multi-transaction extraction",
            invalid_response_error="OpenRouter multi-transaction response was not valid JSON",
            normalize_transaction_payload=False,
        )
        return build_ai_multi_transaction_candidate(raw_input, payload)

    def parse_transaction_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        caption: str = "",
    ) -> ParsedTransaction:
        if not image_bytes:
            raise ValueError("image payload is empty")
        payload = self._call_json_model(
            capability="vision",
            models=self.vision_models,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._image_prompt},
                        {
                            "type": "text",
                            "text": (
                                "Optional user caption:\n"
                                f"{caption.strip() or '-'}\n\n"
                                "Return JSON only."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
                            },
                        },
                    ],
                }
            ],
            empty_response_error="OpenRouter returned an empty response for image parsing",
            invalid_response_error="OpenRouter image response was not valid JSON",
        )
        if not str(payload.get("raw_input") or "").strip():
            payload["raw_input"] = caption.strip() or "image transaction proof"
        try:
            return ParsedTransaction.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"OpenRouter returned invalid image transaction payload: {exc}") from exc

    def correct_transaction(self, original: TransactionRecord, correction_input: str) -> ParsedTransaction:
        if not correction_input.strip():
            raise ValueError("correction input cannot be empty")
        original_payload = {
            "transaction_date": original.transaction_date.isoformat(),
            "type": original.type.value,
            "amount": original.amount,
            "currency": original.currency,
            "category": original.category,
            "subcategory": original.subcategory,
            "account_from": original.account_from,
            "account_to": original.account_to,
            "merchant_or_source": original.merchant_or_source,
            "description": original.description,
            "payment_method": original.payment_method,
            "raw_input": original.raw_input,
        }
        payload = self._call_json_model(
            capability="text",
            models=self.text_models,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{self._correction_prompt}\n\n"
                        f"Original transaction:\n{json.dumps(original_payload, ensure_ascii=False)}\n\n"
                        f"User correction:\n{correction_input}"
                    ),
                }
            ],
            empty_response_error="OpenRouter returned an empty response for transaction correction",
            invalid_response_error="OpenRouter correction response was not valid JSON",
        )
        if not str(payload.get("raw_input") or "").strip():
            payload["raw_input"] = correction_input.strip()
        try:
            return ParsedTransaction.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"OpenRouter returned invalid corrected transaction payload: {exc}") from exc

    def _call_json_model(
        self,
        *,
        capability: str,
        models: tuple[str, ...],
        messages: list[dict[str, Any]],
        empty_response_error: str,
        invalid_response_error: str,
        normalize_transaction_payload: bool = True,
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
                payload = json.loads(GeminiClient._extract_json_text(text))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{invalid_response_error}: {text}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{invalid_response_error}: expected a JSON object, got {type(payload).__name__}")
            if normalize_transaction_payload:
                return GeminiClient._normalize_payload(payload)
            shared_payload = payload.get("shared_payload")
            if isinstance(shared_payload, dict):
                payload["shared_payload"] = GeminiClient._normalize_payload(shared_payload)
            return payload

        return self._run_model_pool(capability, models, operation)

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
        operation,
    ):
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
