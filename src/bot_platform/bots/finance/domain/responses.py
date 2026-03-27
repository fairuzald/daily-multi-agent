from __future__ import annotations

from dataclasses import dataclass

from bot_platform.bots.finance.infrastructure.state_store import ReplyMessageContext


class BotResponse(str):
    def __new__(cls, text: str, reply_context: ReplyMessageContext | None = None):
        obj = str.__new__(cls, text)
        obj.reply_context = reply_context
        return obj


@dataclass
class ReplyContextInput:
    message_id: int | None = None
    is_bot_reply: bool = False
