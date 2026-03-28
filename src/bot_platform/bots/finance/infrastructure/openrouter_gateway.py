from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from bot_platform.bots.finance.domain.multi_transaction import build_ai_multi_transaction_candidate
from bot_platform.bots.finance.infrastructure.gemini_gateway import GeminiClient
from bot_platform.bots.finance.models import ParsedTransaction, TransactionRecord
from bot_platform.shared.ai.openrouter_base import BaseOpenRouterClient


class OpenRouterClient(BaseOpenRouterClient):
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
        super().__init__(
            api_key=api_key,
            text_models=text_models,
            vision_models=vision_models,
            audio_models=audio_models,
            base_url=base_url,
            app_name=app_name,
            http_client=http_client,
        )
        prompt_dir = Path(__file__).resolve().parent.parent / "prompts"
        self._transaction_prompt = GeminiClient.load_prompt(prompt_dir, "transaction_parser.txt")
        self._multi_transaction_prompt = GeminiClient.load_prompt(prompt_dir, "multi_transaction_parser.txt")
        self._image_prompt = GeminiClient.load_prompt(prompt_dir, "receipt_image_parser.txt")
        self._correction_prompt = GeminiClient.load_prompt(prompt_dir, "transaction_correction_parser.txt")

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
            payload_normalizer=GeminiClient._normalize_payload,
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
            payload_normalizer=self._normalize_multi_transaction_payload,
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
            payload_normalizer=GeminiClient._normalize_payload,
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
            payload_normalizer=GeminiClient._normalize_payload,
        )
        if not str(payload.get("raw_input") or "").strip():
            payload["raw_input"] = correction_input.strip()
        try:
            return ParsedTransaction.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"OpenRouter returned invalid corrected transaction payload: {exc}") from exc

    @staticmethod
    def _normalize_multi_transaction_payload(payload: dict[str, Any]) -> dict[str, Any]:
        shared_payload = payload.get("shared_payload")
        if isinstance(shared_payload, dict):
            payload["shared_payload"] = GeminiClient._normalize_payload(shared_payload)
        return payload
