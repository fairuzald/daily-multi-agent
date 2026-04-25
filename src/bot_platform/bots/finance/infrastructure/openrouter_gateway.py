from __future__ import annotations

import base64
import json
from typing import Any

import httpx
from pydantic import ValidationError

from bot_platform.bots.finance.domain.extraction import FinanceMessageExtraction
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
        prompt_dir = GeminiClient.prompt_dir(__file__)
        self._extraction_prompt = GeminiClient.load_prompt(prompt_dir, "finance_message_extractor.txt")

    def extract_message(
        self,
        raw_input: str,
        *,
        reply_context_kind: str = "",
        reply_context_text: str = "",
        pending_kind: str = "",
        message_datetime_iso: str = "",
        image_bytes: bytes | None = None,
        mime_type: str = "image/jpeg",
        caption: str = "",
        original: TransactionRecord | None = None,
    ) -> FinanceMessageExtraction:
        if not raw_input.strip():
            raise ValueError("raw_input cannot be empty")
        context_lines = [
            f"Reply context kind: {reply_context_kind or '-'}",
            f"Reply context text: {reply_context_text.strip() or '-'}",
            f"Pending state kind: {pending_kind or '-'}",
            f"Message datetime: {message_datetime_iso or '-'}",
        ]
        if original is not None:
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
            context_lines.append(f"Original transaction:\n{json.dumps(original_payload, ensure_ascii=False)}")
        if caption.strip():
            context_lines.append(f"Image caption:\n{caption.strip()}")
        prompt_text = f"{self._extraction_prompt}\n\n" + "\n".join(context_lines) + f"\n\nUser input:\n{raw_input}"
        payload = self._call_json_model(
            capability="vision" if image_bytes is not None else "text",
            models=self.vision_models if image_bytes is not None else self.text_models,
            messages=[
                {
                    "role": "user",
                    "content": (
                        [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
                                },
                            },
                        ]
                        if image_bytes is not None
                        else prompt_text
                    ),
                }
            ],
            empty_response_error="OpenRouter returned an empty response for finance extraction",
            invalid_response_error="OpenRouter extraction response was not valid JSON",
        )
        try:
            return GeminiClient._validate_extraction_payload(payload)
        except ValidationError as exc:
            raise ValueError(f"OpenRouter returned invalid extraction payload: {exc}") from exc

    def parse_transaction(self, raw_input: str) -> ParsedTransaction:
        extraction = self.extract_message(raw_input)
        parsed = next((item for item in extraction.items if item.type is not None or item.amount is not None), None)
        if parsed is None:
            raise ValueError("OpenRouter returned invalid transaction payload: no transaction item found")
        return parsed

    def extract_multi_transaction(self, raw_input: str):
        extraction = self.extract_message(raw_input)
        return extraction.to_multi_candidate(raw_input)

    def parse_transaction_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        caption: str = "",
    ) -> ParsedTransaction:
        if not image_bytes:
            raise ValueError("image payload is empty")
        extraction = self.extract_message(
            caption.strip() or "image transaction proof",
            image_bytes=image_bytes,
            mime_type=mime_type,
            caption=caption,
        )
        parsed = next((item for item in extraction.items if item.type is not None or item.amount is not None), None)
        if parsed is None:
            raise ValueError("OpenRouter returned invalid image transaction payload: no transaction item found")
        return parsed

    def correct_transaction(self, original: TransactionRecord, correction_input: str) -> ParsedTransaction:
        if not correction_input.strip():
            raise ValueError("correction input cannot be empty")
        extraction = self.extract_message(
            correction_input,
            original=original,
            reply_context_kind="saved",
        )
        parsed = next((item for item in extraction.items if item.type is not None or item.amount is not None), None)
        if parsed is None:
            raise ValueError("OpenRouter returned invalid corrected transaction payload: no transaction item found")
        return parsed
