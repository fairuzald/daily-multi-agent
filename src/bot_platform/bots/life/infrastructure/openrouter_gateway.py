from __future__ import annotations

import base64
from pathlib import Path

from bot_platform.bots.life.domain.models import ParsedLifeBatch
from bot_platform.bots.life.infrastructure.gemini_gateway import GeminiClient
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
        http_client=None,
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
        self._life_prompt = GeminiClient.load_prompt(prompt_dir, "life_items_parser.txt")
        self._life_correction_prompt = GeminiClient.load_prompt(prompt_dir, "life_items_correction_parser.txt")

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

    def parse_life_items(self, raw_input: str, *, reference_time_iso: str, timezone_name: str) -> ParsedLifeBatch:
        if not raw_input.strip():
            raise ValueError("raw_input cannot be empty")
        payload = self._call_json_model(
            capability="text",
            models=self.text_models,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{self._life_prompt}\n\n"
                        f"Current local datetime: {reference_time_iso}\n"
                        f"Timezone: {timezone_name}\n\n"
                        f"User input:\n{raw_input}"
                    ),
                }
            ],
            empty_response_error="OpenRouter returned an empty response for life parsing",
            invalid_response_error="OpenRouter life parser response was not valid JSON",
        )
        return GeminiClient._normalize_life_batch(payload, fallback_raw_input=raw_input)

    def correct_life_items(
        self,
        *,
        original_input: str,
        correction_input: str,
        reference_time_iso: str,
        timezone_name: str,
    ) -> ParsedLifeBatch:
        payload = self._call_json_model(
            capability="text",
            models=self.text_models,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{self._life_correction_prompt}\n\n"
                        f"Current local datetime: {reference_time_iso}\n"
                        f"Timezone: {timezone_name}\n\n"
                        f"Original input:\n{original_input}\n\n"
                        f"User rewrite or correction:\n{correction_input}"
                    ),
                }
            ],
            empty_response_error="OpenRouter returned an empty response for life correction",
            invalid_response_error="OpenRouter life correction response was not valid JSON",
        )
        return GeminiClient._normalize_life_batch(payload, fallback_raw_input=correction_input or original_input)
