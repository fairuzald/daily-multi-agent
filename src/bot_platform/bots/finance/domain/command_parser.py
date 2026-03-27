from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedCommand:
    intent: str = ""
    target: str = ""
    query: str = ""
    category: str = ""
    period: str = ""
    amount: int | None = None
    extra: dict[str, str] = field(default_factory=dict)


class CommandParser:
    DELETE_WORDS = ("delete", "hapus", "remove")
    EDIT_WORDS = ("edit", "ubah", "change")
    READ_WORDS = ("show", "read", "lihat", "berapa")

    def parse(self, text: str) -> ParsedCommand:
        lowered = text.strip().lower()

        if any(lowered.startswith(word) for word in self.DELETE_WORDS):
            target = "reply" if "this" in lowered or "ini" in lowered else "last"
            return ParsedCommand(intent="delete", target=target, query=text)

        if any(lowered.startswith(word) for word in self.EDIT_WORDS):
            target = "reply" if "this" in lowered or "ini" in lowered else "last"
            return ParsedCommand(intent="edit", target=target, query=text)

        if lowered.startswith("set ") and ("budget" in lowered or "limit" in lowered):
            amount_match = re.search(r"(\d[\d\.]*)", lowered)
            amount = int(re.sub(r"\D", "", amount_match.group(1))) if amount_match else None
            period = "weekly" if "weekly" in lowered or "mingguan" in lowered or "week" in lowered else "monthly"
            category_match = re.search(r"for ([a-zA-Z ]+?) limit|for ([a-zA-Z ]+?) budget|kategori ([a-zA-Z ]+)", lowered)
            category = ""
            if category_match:
                category = next((group.strip() for group in category_match.groups() if group), "")
            scope = "category" if category else "global"
            return ParsedCommand(intent="budget_set", amount=amount, period=period, category=category.title(), target=scope)

        if "show budget" in lowered or "budget " in lowered and any(word in lowered for word in ("show", "lihat", "berapa")):
            period = "weekly" if "week" in lowered or "minggu" in lowered else "monthly"
            return ParsedCommand(intent="budget_show", period=period, query=text)

        if "compare" in lowered and "month" in lowered:
            return ParsedCommand(intent="compare_month", query=text)

        if any(lowered.startswith(word) for word in self.READ_WORDS):
            period = ""
            if "today" in lowered or "hari ini" in lowered:
                period = "today"
            elif "week" in lowered or "minggu" in lowered:
                period = "week"
            elif "month" in lowered or "bulan" in lowered:
                period = "month"
            return ParsedCommand(intent="read", period=period, query=text)

        return ParsedCommand()
