from __future__ import annotations

class LifeBotResponse(str):
    def __new__(cls, text: str, reply_context: object | None = None):
        obj = str.__new__(cls, text)
        obj.reply_context = reply_context
        return obj
