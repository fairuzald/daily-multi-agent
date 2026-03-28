from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from google.genai import types
from pydantic import ValidationError

from bot_platform.bots.finance.models import ParsedTransaction, TransactionRecord


class SourceKind(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"


class GeminiClient:
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._transaction_prompt = self._load_prompt("transaction_parser.txt")
        self._image_prompt = self._load_prompt("receipt_image_parser.txt")
        self._correction_prompt = self._load_prompt("transaction_correction_parser.txt")

    @staticmethod
    def _load_prompt(file_name: str) -> str:
        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / file_name
        return prompt_path.read_text(encoding="utf-8")

    def transcribe_voice_note(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        if not audio_bytes:
            raise ValueError("audio payload is empty")
        try:
            from google import genai  # type: ignore
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed. Run `poetry install` first.") from exc

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=self.model_name,
            contents=[
                types.Part.from_text(
                    text=(
                        "Transcribe this Indonesian Telegram voice note. "
                        "Return only the spoken transcript text without Markdown or explanation."
                    )
                ),
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
        )

        transcript = (getattr(response, "text", "") or "").strip()
        if not transcript:
            raise ValueError("Gemini returned an empty transcription")
        return transcript

    def parse_transaction(self, raw_input: str) -> ParsedTransaction:
        if not raw_input.strip():
            raise ValueError("raw_input cannot be empty")
        payload = self._call_model(raw_input)
        try:
            parsed = ParsedTransaction.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Gemini returned invalid transaction payload: {exc}") from exc
        return parsed

    def parse_transaction_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        caption: str = "",
    ) -> ParsedTransaction:
        if not image_bytes:
            raise ValueError("image payload is empty")
        payload = self._call_image_model(image_bytes=image_bytes, mime_type=mime_type, caption=caption)
        try:
            parsed = ParsedTransaction.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Gemini returned invalid image transaction payload: {exc}") from exc
        return parsed

    def correct_transaction(self, original: TransactionRecord, correction_input: str) -> ParsedTransaction:
        if not correction_input.strip():
            raise ValueError("correction input cannot be empty")
        payload = self._call_correction_model(original=original, correction_input=correction_input)
        try:
            parsed = ParsedTransaction.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Gemini returned invalid corrected transaction payload: {exc}") from exc
        return parsed

    def _call_model(self, raw_input: str) -> dict[str, Any]:
        try:
            from google import genai  # type: ignore
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed. Run `poetry install` first.") from exc

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=self.model_name,
            contents=f"{self._transaction_prompt}\n\nUser input:\n{raw_input}",
        )

        text = getattr(response, "text", "") or ""
        if not text:
            raise ValueError("Gemini returned an empty response")

        try:
            return self._normalize_payload(json.loads(self._extract_json_text(text)))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Gemini response was not valid JSON: {text}") from exc

    def _call_image_model(self, image_bytes: bytes, mime_type: str, caption: str) -> dict[str, Any]:
        try:
            from google import genai  # type: ignore
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed. Run `poetry install` first.") from exc

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=self.model_name,
            contents=[
                types.Part.from_text(text=self._image_prompt),
                types.Part.from_text(
                    text=(
                        "Optional user caption:\n"
                        f"{caption.strip() or '-'}\n\n"
                        "Return JSON only."
                    )
                ),
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
        )

        text = getattr(response, "text", "") or ""
        if not text:
            raise ValueError("Gemini returned an empty response for image parsing")

        try:
            payload = self._normalize_payload(json.loads(self._extract_json_text(text)))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Gemini image response was not valid JSON: {text}") from exc

        if not str(payload.get("raw_input") or "").strip():
            payload["raw_input"] = caption.strip() or "image transaction proof"
        return payload

    def _call_correction_model(self, original: TransactionRecord, correction_input: str) -> dict[str, Any]:
        try:
            from google import genai  # type: ignore
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed. Run `poetry install` first.") from exc

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

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=self.model_name,
            contents=(
                f"{self._correction_prompt}\n\n"
                f"Original transaction:\n{json.dumps(original_payload, ensure_ascii=False)}\n\n"
                f"User correction:\n{correction_input}"
            ),
        )

        text = getattr(response, "text", "") or ""
        if not text:
            raise ValueError("Gemini returned an empty response for transaction correction")

        try:
            payload = self._normalize_payload(json.loads(self._extract_json_text(text)))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Gemini correction response was not valid JSON: {text}") from exc

        if not str(payload.get("raw_input") or "").strip():
            payload["raw_input"] = correction_input.strip()
        return payload

    @staticmethod
    def _extract_json_text(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        return stripped

    @staticmethod
    def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)

        if normalized.get("type") is None:
            normalized["type"] = None

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
        if value in (None, ""):
            return None
        if isinstance(value, str):
            digits = "".join(char for char in value if char.isdigit())
            if not digits:
                return None
            value = int(digits)
        if isinstance(value, float):
            value = int(value)
        if not isinstance(value, int):
            return None
        return value if value > 0 else None

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
