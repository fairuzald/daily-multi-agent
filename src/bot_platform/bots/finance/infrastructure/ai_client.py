from __future__ import annotations

from typing import Protocol

from bot_platform.bots.finance.domain.extraction import FinanceMessageExtraction
from bot_platform.bots.finance.domain.multi_transaction import MultiTransactionCandidate
from bot_platform.bots.finance.models import ParsedTransaction, TransactionRecord
from bot_platform.shared.ai.provider_exhaustion import AIProviderExhaustion, detect_provider_exhaustion


class AIClient(Protocol):
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
    ) -> FinanceMessageExtraction: ...

    def parse_transaction(self, raw_input: str) -> ParsedTransaction: ...

    def extract_multi_transaction(self, raw_input: str) -> MultiTransactionCandidate | None: ...

    def parse_transaction_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        caption: str = "",
    ) -> ParsedTransaction: ...

    def correct_transaction(self, original: TransactionRecord, correction_input: str) -> ParsedTransaction: ...

    def transcribe_voice_note(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str: ...
