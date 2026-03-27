import asyncio
from datetime import datetime

from bot_platform.bots.finance.interfaces.telegram.controller import TelegramBotController, humanize_processing_error
from bot_platform.bots.finance.models import ParsedTransaction


class FakeVoice:
    def __init__(self, file_id: str, mime_type: str = "audio/ogg") -> None:
        self.file_id = file_id
        self.mime_type = mime_type


class FakeMessage:
    def __init__(self) -> None:
        self.voice = FakeVoice("voice-file-id")
        self.photo = []
        self.document = None
        self.caption = ""
        self.reply_to_message = None
        self.replies: list[str] = []
        self.date = datetime(2026, 3, 27, 9, 0, 0)

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)
        return type("SentMessage", (), {"message_id": len(self.replies)})()


class FakeTelegramFile:
    async def download_as_bytearray(self):
        return bytearray(b"fake-audio")


class FakeBot:
    async def get_file(self, file_id: str):
        assert file_id == "voice-file-id"
        return FakeTelegramFile()


class FakeGeminiClient:
    def transcribe_voice_note(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        assert audio_bytes == b"fake-audio"
        assert mime_type == "audio/ogg"
        return "beli kopi 20000 pakai bca"

    def parse_transaction_image(self, image_bytes: bytes, mime_type: str = "image/jpeg", caption: str = "") -> ParsedTransaction:
        assert image_bytes == b"fake-audio"
        assert mime_type == "image/jpeg"
        assert caption == "tagihan listrik"
        return ParsedTransaction(
            type="expense",
            amount=125000,
            category="Bills",
            subcategory="Electricity",
            raw_input="tagihan listrik",
            confidence=0.93,
        )


class FakeBotService:
    def __init__(self) -> None:
        self.gemini_client = FakeGeminiClient()
        self.state_store = type("StateStore", (), {"set_reply_context": lambda *args, **kwargs: None})()

    def handle_voice_transcript(
        self,
        user_id: int,
        chat_id: int,
        transcript: str,
        reply_context=None,
        message_datetime=None,
    ) -> str:
        assert user_id == 123
        assert chat_id == 456
        assert transcript == "beli kopi 20000 pakai bca"
        assert message_datetime is not None
        return "Saved from voice"

    def handle_image_message(
        self,
        user_id: int,
        chat_id: int,
        parsed: ParsedTransaction,
        reply_context=None,
        message_datetime=None,
    ) -> str:
        assert user_id == 123
        assert chat_id == 456
        assert parsed.amount == 125000
        assert parsed.category == "Bills"
        assert message_datetime is not None
        return "Saved from image"


class FakeContext:
    def __init__(self) -> None:
        self.application = type("App", (), {"bot_data": {}})()
        self.bot = FakeBot()


class FakeUpdate:
    def __init__(self) -> None:
        self.message = FakeMessage()
        self.effective_user = type("User", (), {"id": 123})()
        self.effective_chat = type("Chat", (), {"id": 456})()


def test_voice_message_replies_after_transcription() -> None:
    update = FakeUpdate()
    context = FakeContext()
    controller = TelegramBotController(FakeBotService())

    asyncio.run(controller.voice_message(update, context))

    assert update.message.replies == ["Saved from voice"]


def test_photo_message_replies_after_image_parsing() -> None:
    update = FakeUpdate()
    update.message.photo = [type("Photo", (), {"file_id": "voice-file-id"})()]
    update.message.caption = "tagihan listrik"
    context = FakeContext()
    controller = TelegramBotController(FakeBotService())

    asyncio.run(controller.photo_message(update, context))

    assert update.message.replies == ["Saved from image"]


def test_humanize_processing_error_for_quota_limit() -> None:
    reply = humanize_processing_error(
        Exception("429 RESOURCE_EXHAUSTED. Please retry in 39.756211463s."),
        source="voice note",
    )

    assert "temporarily exhausted" in reply
    assert "39 seconds" in reply


def test_humanize_processing_error_for_timeout() -> None:
    reply = humanize_processing_error(
        Exception("request timeout while calling upstream"),
        source="image",
    )

    assert "took too long" in reply
    assert "image" in reply
