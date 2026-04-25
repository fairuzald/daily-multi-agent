from __future__ import annotations

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
        prompt_dir = GeminiClient.prompt_dir(__file__)
        self._life_prompt = GeminiClient.load_prompt(prompt_dir, "life_message_extractor.txt")

    def extract_life_items(
        self,
        raw_input: str,
        *,
        original_input: str = "",
        reference_time_iso: str,
        timezone_name: str,
    ) -> ParsedLifeBatch:
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
                        f"{GeminiClient._build_user_block(raw_input=raw_input, original_input=original_input, reference_time_iso=reference_time_iso, timezone_name=timezone_name)}"
                    ),
                }
            ],
            empty_response_error="OpenRouter returned an empty response for life extraction",
            invalid_response_error="OpenRouter life extractor response was not valid JSON",
        )
        return GeminiClient._normalize_life_batch(payload, fallback_raw_input=raw_input or original_input)
