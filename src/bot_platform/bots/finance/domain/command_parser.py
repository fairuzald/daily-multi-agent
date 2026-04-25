from __future__ import annotations

import re
from dataclasses import dataclass, field

from bot_platform.bots.finance.domain.amounts import parse_amount_expression
from bot_platform.bots.finance.domain.language import (
    COMPARE_TOKENS,
    CORRECTION_FILLER_TOKENS,
    DELETE_WORDS,
    EDIT_PREFIXES,
    MONTH_TOKENS,
    READ_BUDGET_TOKENS,
    READ_WORDS,
    REFERENCE_TARGET_TOKENS,
    SUMMARY_TOKENS,
    TODAY_TOKENS,
    WEEK_TOKENS,
)


@dataclass(frozen=True)
class ParsedCommand:
    intent: str = ""
    target: str = ""
    query: str = ""
    category: str = ""
    period: str = ""
    amount: int | None = None
    correction_text: str = ""
    extra: dict[str, str] = field(default_factory=dict)


class CommandParser:
    def parse(self, text: str) -> ParsedCommand:
        normalized = " ".join(text.strip().split())
        lowered = normalized.lower()

        compare_command = self._parse_compare_command(normalized, lowered)
        if compare_command.intent:
            return compare_command

        summary_command = self._parse_summary_command(normalized, lowered)
        if summary_command.intent:
            return summary_command

        delete_command = self._parse_delete_command(normalized, lowered)
        if delete_command.intent:
            return delete_command

        edit_command = self._parse_edit_command(normalized, lowered)
        if edit_command.intent:
            return edit_command

        if lowered.startswith("set ") and ("budget" in lowered or "limit" in lowered):
            amount_match = re.search(r"(\d[\d\.,]*(?:\s*(?:k|rb|ribu|jt|juta|mil))?)", lowered)
            amount = parse_amount_expression(amount_match.group(1)) if amount_match else None
            period = "weekly" if "weekly" in lowered or "mingguan" in lowered or "week" in lowered else "monthly"
            category_match = re.search(r"for ([a-zA-Z ]+?) limit|for ([a-zA-Z ]+?) budget|kategori ([a-zA-Z ]+)", lowered)
            category = ""
            if category_match:
                category = next((group.strip() for group in category_match.groups() if group), "")
            scope = "category" if category else "global"
            return ParsedCommand(intent="budget_set", amount=amount, period=period, category=category.title(), target=scope)

        if "show budget" in lowered or "budget " in lowered and any(word in lowered for word in READ_BUDGET_TOKENS):
            period = "weekly" if "week" in lowered or "minggu" in lowered else "monthly"
            return ParsedCommand(intent="budget_show", period=period, query=text)

        if any(lowered.startswith(word) for word in READ_WORDS):
            period = ""
            if any(token in lowered for token in TODAY_TOKENS):
                period = "today"
            elif any(token in lowered for token in WEEK_TOKENS):
                period = "week"
            elif any(token in lowered for token in MONTH_TOKENS):
                period = "month"
            return ParsedCommand(intent="read", period=period, query=text)

        return ParsedCommand()

    @staticmethod
    def _parse_compare_command(normalized: str, lowered: str) -> ParsedCommand:
        if any(token in lowered for token in COMPARE_TOKENS) and any(token in lowered for token in MONTH_TOKENS):
            return ParsedCommand(intent="compare_month", query=normalized)
        return ParsedCommand()

    @staticmethod
    def _parse_summary_command(normalized: str, lowered: str) -> ParsedCommand:
        if not any(token in lowered for token in SUMMARY_TOKENS):
            return ParsedCommand()
        period = ""
        if any(token in lowered for token in TODAY_TOKENS):
            period = "today"
        elif any(token in lowered for token in WEEK_TOKENS):
            period = "week"
        elif any(token in lowered for token in MONTH_TOKENS):
            period = "month"
        return ParsedCommand(intent="summary", period=period or "month", query=normalized)

    def _parse_delete_command(self, normalized: str, lowered: str) -> ParsedCommand:
        delete_words_pattern = "|".join(re.escape(word) for word in DELETE_WORDS)
        reference_tokens_pattern = "|".join(re.escape(word) for word in REFERENCE_TARGET_TOKENS)
        if not any(lowered.startswith(word) for word in DELETE_WORDS):
            if not re.search(rf"\b(?:{delete_words_pattern})\s+(?:{reference_tokens_pattern})\b", lowered):
                return ParsedCommand()
        target = "reply" if re.search(rf"\b(?:{reference_tokens_pattern})\b", lowered) else "last"
        return ParsedCommand(intent="delete", target=target, query=normalized)

    def _parse_edit_command(self, normalized: str, lowered: str) -> ParsedCommand:
        prefix = self._matched_edit_prefix(lowered)
        if prefix is None:
            return ParsedCommand()
        reference_tokens_pattern = "|".join(re.escape(word) for word in REFERENCE_TARGET_TOKENS)
        target = "reply" if re.search(rf"\b(?:{reference_tokens_pattern})\b", lowered) else "last"
        correction_text = self._extract_correction_text(normalized, lowered, prefix)
        return ParsedCommand(intent="edit", target=target, query=normalized, correction_text=correction_text)

    @staticmethod
    def _matched_edit_prefix(lowered: str) -> str | None:
        for prefix in EDIT_PREFIXES:
            if lowered.startswith(prefix):
                return prefix
        return None

    @staticmethod
    def _extract_correction_text(normalized: str, lowered: str, prefix: str) -> str:
        correction = normalized[len(prefix):].strip()
        if correction.lower() in CORRECTION_FILLER_TOKENS:
            return ""
        if correction:
            return correction
        match = re.search(r"\b(?:jadi|ke)\s+(.+)$", normalized, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""
