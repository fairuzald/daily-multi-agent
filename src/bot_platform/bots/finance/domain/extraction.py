from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from bot_platform.bots.finance.domain.amounts import parse_amount_expression
from bot_platform.bots.finance.domain.command_parser import ParsedCommand
from bot_platform.bots.finance.domain.multi_transaction import MultiTransactionCandidate
from bot_platform.bots.finance.models import ParsedTransaction


class FinanceMessageExtraction(BaseModel):
    intent: Literal[
        "transaction",
        "edit",
        "delete",
        "summary",
        "compare_month",
        "read",
        "budget_set",
        "budget_show",
        "clarify",
        "unknown",
    ] = "unknown"
    target: str = ""
    period: str = ""
    category: str = ""
    amount: int | None = None
    correction_text: str = ""
    clarification_message: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    multi_kind: Literal["single", "explicit", "ambiguous"] = "single"
    shared_total_amount: int | None = None
    items: list[ParsedTransaction] = Field(default_factory=list)
    shared_payload: ParsedTransaction | None = None

    @field_validator("amount", "shared_total_amount", mode="before")
    @classmethod
    def _normalize_amounts(cls, value: object) -> int | None:
        return parse_amount_expression(value)

    @field_validator("target", mode="before")
    @classmethod
    def _normalize_target(cls, value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"reply", "replied", "this"}:
            return "reply"
        if normalized in {"last", "latest", "recent"}:
            return "last"
        return ""

    @field_validator("period", mode="before")
    @classmethod
    def _normalize_period(cls, value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"today", "hari ini"}:
            return "today"
        if normalized in {"week", "minggu", "weekly"}:
            return "week"
        if normalized in {"month", "bulan", "monthly"}:
            return "month"
        return ""

    def to_command(self, query: str) -> ParsedCommand:
        return ParsedCommand(
            intent="" if self.intent == "transaction" else self.intent,
            target=self.target,
            query=query,
            category=self.category,
            period=self.period,
            amount=self.amount,
            correction_text=self.correction_text,
        )

    def to_multi_candidate(self, raw_input: str) -> MultiTransactionCandidate | None:
        if len(self.items) < 2:
            return None
        item_labels = [self._item_label(item) for item in self.items]
        item_inputs = [item.raw_input.strip() or label for item, label in zip(self.items, item_labels, strict=False)]
        shared_payload = self.shared_payload.model_dump(mode="json") if self.shared_payload is not None else None
        return MultiTransactionCandidate(
            kind=self.multi_kind,
            raw_input=raw_input,
            item_inputs=item_inputs,
            item_labels=item_labels,
            shared_total_amount=self.shared_total_amount,
            item_amounts=[item.amount for item in self.items],
            shared_payload=shared_payload,
            parsed_items=self.items,
        )

    @staticmethod
    def _item_label(item: ParsedTransaction) -> str:
        return (
            item.subcategory.strip()
            or item.description.strip()
            or item.merchant_or_source.strip()
            or item.raw_input.strip()
            or "Item"
        )
