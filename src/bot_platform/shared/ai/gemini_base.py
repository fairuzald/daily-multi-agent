from __future__ import annotations

from pathlib import Path

from google.genai import types


class BaseGeminiClient:
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        self.api_key = api_key
        self.model_name = model_name

    @staticmethod
    def load_prompt(prompt_dir: Path, file_name: str) -> str:
        prompt_path = prompt_dir / file_name
        return prompt_path.read_text(encoding="utf-8")

    @staticmethod
    def extract_json_text(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        return stripped

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
