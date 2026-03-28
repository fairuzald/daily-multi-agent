from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from bot_platform.bots.life.domain.models import ParsedLifeBatch, ParsedLifeItem, LifeItemType
from bot_platform.shared.ai.gemini_base import BaseGeminiClient


class GeminiClient(BaseGeminiClient):
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        super().__init__(api_key=api_key, model_name=model_name)
        prompt_dir = Path(__file__).resolve().parent.parent / "prompts"
        self._life_prompt = self.load_prompt(prompt_dir, "life_items_parser.txt")
        self._life_correction_prompt = self.load_prompt(prompt_dir, "life_items_correction_parser.txt")

    def parse_life_items(self, raw_input: str, *, reference_time_iso: str, timezone_name: str) -> ParsedLifeBatch:
        if not raw_input.strip():
            raise ValueError("raw_input cannot be empty")
        payload = self._call_life_model(
            prompt=self._life_prompt,
            user_block=(
                f"Current local datetime: {reference_time_iso}\n"
                f"Timezone: {timezone_name}\n\n"
                f"User input:\n{raw_input}"
            ),
        )
        return self._normalize_life_batch(payload, fallback_raw_input=raw_input)

    def correct_life_items(
        self,
        *,
        original_input: str,
        correction_input: str,
        reference_time_iso: str,
        timezone_name: str,
    ) -> ParsedLifeBatch:
        payload = self._call_life_model(
            prompt=self._life_correction_prompt,
            user_block=(
                f"Current local datetime: {reference_time_iso}\n"
                f"Timezone: {timezone_name}\n\n"
                f"Original input:\n{original_input}\n\n"
                f"User rewrite or correction:\n{correction_input}"
            ),
        )
        return self._normalize_life_batch(payload, fallback_raw_input=correction_input or original_input)

    def _call_life_model(self, *, prompt: str, user_block: str) -> dict[str, Any]:
        try:
            from google import genai  # type: ignore
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed. Run `poetry install` first.") from exc

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=self.model_name,
            contents=f"{prompt}\n\n{user_block}",
        )

        text = getattr(response, "text", "") or ""
        if not text:
            raise ValueError("Gemini returned an empty response")
        try:
            payload = json.loads(self.extract_json_text(text))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Gemini life parser response was not valid JSON: {text}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Gemini life parser response was not valid JSON: expected a JSON object, got {type(payload).__name__}")
        return payload

    @classmethod
    def _normalize_life_batch(cls, payload: dict[str, Any], *, fallback_raw_input: str) -> ParsedLifeBatch:
        items_payload = payload.get("items")
        needs_manual_review = bool(payload.get("needs_manual_review"))
        manual_guidance = str(payload.get("manual_guidance") or "").strip()

        if items_payload is None:
            items_payload = []
        if not isinstance(items_payload, list):
            raise ValueError("AI life parser returned invalid payload: `items` must be a list.")

        items: list[ParsedLifeItem] = []
        for item_payload in items_payload:
            if not isinstance(item_payload, dict):
                raise ValueError("AI life parser returned invalid payload: each item must be an object.")
            normalized_item = cls._normalize_life_item_payload(item_payload, fallback_raw_input=fallback_raw_input)
            try:
                items.append(ParsedLifeItem.model_validate(normalized_item))
            except ValidationError as exc:
                raise ValueError(f"AI life parser returned invalid life item payload: {exc}") from exc

        if not items and not needs_manual_review:
            needs_manual_review = True
        return ParsedLifeBatch(items=items, needs_manual_review=needs_manual_review, manual_guidance=manual_guidance)

    @staticmethod
    def _normalize_life_item_payload(item_payload: dict[str, Any], *, fallback_raw_input: str) -> dict[str, Any]:
        normalized = dict(item_payload)
        normalized["type"] = GeminiClient._normalize_life_item_type(normalized.get("type"))
        for field_name in ("title", "person", "details", "recurrence", "raw_input"):
            if normalized.get(field_name) is None:
                normalized[field_name] = ""
            else:
                normalized[field_name] = str(normalized[field_name]).strip()
        if not normalized["raw_input"]:
            normalized["raw_input"] = fallback_raw_input
        for field_name in ("due_at", "remind_at"):
            if normalized.get(field_name) in ("", None):
                normalized[field_name] = None
        normalized["all_day"] = bool(normalized.get("all_day", True))
        return normalized

    @staticmethod
    def _normalize_life_item_type(value: Any) -> str | None:
        if value in (None, ""):
            return None
        normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        mapping = {
            "task": LifeItemType.TASK.value,
            "reminder": LifeItemType.REMINDER.value,
            "follow_up": LifeItemType.FOLLOW_UP.value,
            "followup": LifeItemType.FOLLOW_UP.value,
            "important_date": LifeItemType.IMPORTANT_DATE.value,
            "importantdate": LifeItemType.IMPORTANT_DATE.value,
            "date": LifeItemType.IMPORTANT_DATE.value,
        }
        return mapping.get(normalized, normalized)
