from __future__ import annotations

from dataclasses import dataclass


class BotResponse(str):
    def __new__(cls, text: str, reply_context: object | None = None):
        obj = str.__new__(cls, text)
        obj.reply_context = reply_context
        return obj


@dataclass
class ReplyContextInput:
    message_id: int | None = None
    is_bot_reply: bool = False
    message_text: str = ""
