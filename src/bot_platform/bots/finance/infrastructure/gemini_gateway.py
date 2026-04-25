from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from google.genai import types
from pydantic import ValidationError

from bot_platform.bots.finance.domain.amounts import parse_amount_expression
from bot_platform.bots.finance.domain.extraction import FinanceMessageExtraction
from bot_platform.bots.finance.domain.multi_transaction import build_ai_multi_transaction_candidate
from bot_platform.bots.finance.models import ParsedTransaction, TransactionRecord
from bot_platform.shared.ai.gemini_base import BaseGeminiClient


class SourceKind(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"


class GeminiClient(BaseGeminiClient):
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        super().__init__(api_key=api_key, model_name=model_name)
        prompt_dir = self.prompt_dir(__file__)
        self._extraction_prompt = self.load_prompt(prompt_dir, "finance_message_extractor.txt")

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
        payload = self._call_extraction_model(
            raw_input,
            reply_context_kind=reply_context_kind,
            reply_context_text=reply_context_text,
            pending_kind=pending_kind,
            message_datetime_iso=message_datetime_iso,
            image_bytes=image_bytes,
            mime_type=mime_type,
            caption=caption,
            original=original,
        )
        try:
            return self._validate_extraction_payload(payload)
        except ValidationError as exc:
            raise ValueError(f"Gemini returned invalid extraction payload: {exc}") from exc

    def parse_transaction(self, raw_input: str) -> ParsedTransaction:
        extraction = self.extract_message(raw_input)
        parsed = next((item for item in extraction.items if item.type is not None or item.amount is not None), None)
        if parsed is None:
            raise ValueError("Gemini returned invalid transaction payload: no transaction item found")
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
            raise ValueError("Gemini returned invalid image transaction payload: no transaction item found")
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
            raise ValueError("Gemini returned invalid corrected transaction payload: no transaction item found")
        return parsed

    def _call_extraction_model(
        self,
        raw_input: str,
        *,
        reply_context_kind: str,
        reply_context_text: str,
        pending_kind: str,
        message_datetime_iso: str,
        image_bytes: bytes | None,
        mime_type: str,
        caption: str,
        original: TransactionRecord | None,
    ) -> dict[str, Any]:
        try:
            from google import genai  # type: ignore
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed. Run `poetry install` first.") from exc

        client = genai.Client(api_key=self.api_key)
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
        if image_bytes is None:
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt_text,
            )
        else:
            response = client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_text(text=prompt_text),
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
            )

        text = getattr(response, "text", "") or ""
        if not text:
            raise ValueError("Gemini returned an empty response for finance extraction")

        try:
            payload = json.loads(self.extract_json_text(text))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Gemini extraction response was not valid JSON: {text}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Gemini extraction response was not valid JSON: expected a JSON object, got {type(payload).__name__}")
        return payload

    @classmethod
    def _validate_extraction_payload(cls, payload: dict[str, Any]) -> FinanceMessageExtraction:
        normalized = dict(payload)
        items_payload = normalized.get("items")
        validated_items: list[ParsedTransaction] = []
        if isinstance(items_payload, list):
            for raw_item in items_payload:
                if not isinstance(raw_item, dict):
                    continue
                validated_items.append(ParsedTransaction.model_validate(cls._normalize_payload(raw_item)))
        normalized["items"] = validated_items

        shared_payload = normalized.get("shared_payload")
        if isinstance(shared_payload, dict):
            normalized["shared_payload"] = ParsedTransaction.model_validate(cls._normalize_payload(shared_payload))
        else:
            normalized["shared_payload"] = None

        return FinanceMessageExtraction.model_validate(normalized)

    @staticmethod
    def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)

        if normalized.get("type") is None:
            normalized["type"] = None
        else:
            normalized["type"] = GeminiClient._normalize_transaction_type(normalized.get("type"))

        for field_name in (
            "currency",
            "category",
            "subcategory",
            "account_from",
            "account_to",
            "merchant_or_source",
            "description",
            "payment_method",
            "raw_input",
        ):
            if normalized.get(field_name) is None:
                normalized[field_name] = ""

        transaction_date = normalized.get("transaction_date")
        if transaction_date in (None, "", "today", "hari ini", "barusan"):
            normalized["transaction_date"] = date.today().isoformat()
        elif isinstance(transaction_date, str):
            stripped_date = transaction_date.strip()
            if GeminiClient._looks_like_placeholder_date(stripped_date):
                normalized["transaction_date"] = date.today().isoformat()
                normalized["needs_confirmation"] = True
            elif stripped_date:
                try:
                    normalized["transaction_date"] = datetime.fromisoformat(
                        stripped_date.replace("Z", "+00:00")
                    ).date().isoformat()
                except ValueError:
                    normalized["transaction_date"] = date.today().isoformat()
                    normalized["needs_confirmation"] = True

        if normalized.get("tags") is None:
            normalized["tags"] = []

        if normalized.get("missing_fields") is None:
            normalized["missing_fields"] = []
        else:
            normalized["missing_fields"] = GeminiClient._filter_required_missing_fields(normalized)

        if normalized.get("type") is None and "type" not in normalized["missing_fields"]:
            normalized["missing_fields"].insert(0, "type")
        normalized["amount"] = GeminiClient._normalize_amount(normalized.get("amount"))
        if normalized.get("amount") in (None, "") and "amount" not in normalized["missing_fields"]:
            normalized["missing_fields"].append("amount")
        if normalized.get("type") != "transfer":
            normalized["account_to"] = ""

        raw_context = " ".join(
            str(normalized.get(field_name) or "")
            for field_name in ("raw_input", "merchant_or_source", "description")
        )
        normalized["payment_method"] = GeminiClient._normalize_payment_method(
            normalized.get("payment_method"),
            raw_context=raw_context,
        )
        normalized["account_from"] = GeminiClient._normalize_payment_method(
            normalized.get("account_from"),
            raw_context=raw_context,
        )
        if normalized.get("type") == "transfer":
            normalized["account_to"] = GeminiClient._normalize_payment_method(
                normalized.get("account_to"),
                raw_context=raw_context,
            )

        if normalized.get("transaction_date"):
            normalized["needs_confirmation"] = bool(normalized.get("missing_fields")) or bool(
                normalized.get("needs_confirmation")
            )
        return normalized

    @staticmethod
    def _normalize_transaction_type(value: Any) -> str | None:
        if value in (None, ""):
            return None
        normalized = str(value).strip().lower()
        type_map = {
            "expense": "expense",
            "pengeluaran": "expense",
            "income": "income",
            "pemasukan": "income",
            "transfer": "transfer",
            "investment in": "investment_in",
            "investment_in": "investment_in",
            "investasi masuk": "investment_in",
            "investment out": "investment_out",
            "investment_out": "investment_out",
            "investasi keluar": "investment_out",
        }
        return type_map.get(normalized, normalized)

    @staticmethod
    def _looks_like_placeholder_date(value: str) -> bool:
        lowered = value.strip().lower()
        if lowered in {"yyyy-mm-dd", "dd-mm-yyyy", "dd/mm/yyyy", "mm-dd-yyyy", "mm/dd/yyyy"}:
            return True
        return any(token in lowered for token in ("yyyy", "mm", "dd")) and any(char in lowered for char in ("-", "/"))

    @staticmethod
    def _filter_required_missing_fields(payload: dict[str, Any]) -> list[str]:
        tx_type = str(payload.get("type") or "")
        required_by_type = {
            "expense": {"type", "amount", "subcategory", "description", "payment_method"},
            "income": {"type", "amount", "subcategory", "description", "payment_method"},
            "investment_in": {"type", "amount", "subcategory", "description", "payment_method"},
            "investment_out": {"type", "amount", "subcategory", "description", "payment_method"},
            "transfer": {"type", "amount", "subcategory", "description", "payment_method", "account_to"},
        }
        required = required_by_type.get(tx_type, {"type", "amount"})
        return [
            field_name
            for field_name in payload.get("missing_fields", [])
            if field_name in required and field_name != "transaction_date"
        ]

    @staticmethod
    def _normalize_amount(value: Any) -> int | None:
        return parse_amount_expression(value)

    @staticmethod
    def _normalize_payment_method(value: Any, *, raw_context: str = "") -> str:
        text = str(value or "").strip()
        context = f"{text} {raw_context}".lower()
        if not context.strip():
            return ""

        if "gopay" in context or "go pay" in context or "go-pay" in context:
            return "GoPay"
        if "shopeepay" in context or "shopee pay" in context or "shopee-pay" in context:
            return "ShopeePay"
        if "dana" in context:
            return "DANA"
        if "bca" in context:
            return "BCA"
        if "bri" in context:
            return "BRI"
        if "cash" in context or "tunai" in context:
            return "Cash"
        if "qris" in context:
            return "QRIS"
        if "bank transfer" in context or "transfer bank" in context or text.lower() == "transfer":
            return "Bank Transfer"
        if "e-wallet" in context or "ewallet" in context or "dompet digital" in context:
            if "gopay" in context or "go pay" in context or "go-pay" in context:
                return "GoPay"
            if "shopeepay" in context or "shopee pay" in context or "shopee-pay" in context:
                return "ShopeePay"
            if "dana" in context:
                return "DANA"
            return "E-Wallet"

        return text
