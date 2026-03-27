from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class TransactionType(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"
    INVESTMENT_IN = "investment_in"
    INVESTMENT_OUT = "investment_out"


class InputMode(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"


class TransactionStatus(str, Enum):
    CONFIRMED = "confirmed"
    EDITED = "edited"
    DELETED = "deleted"
    PENDING = "pending"


class TransactionRecord(BaseModel):
    transaction_id: str = Field(default_factory=lambda: f"txn_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    transaction_date: date = Field(default_factory=date.today)
    type: TransactionType
    amount: int = Field(gt=0)
    currency: str = "IDR"
    category: str
    subcategory: str = ""
    account_from: str = ""
    account_to: str = ""
    merchant_or_source: str = ""
    description: str = ""
    payment_method: str = ""
    tags: list[str] = Field(default_factory=list)
    input_mode: InputMode = InputMode.TEXT
    raw_input: str = ""
    ai_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: TransactionStatus = TransactionStatus.CONFIRMED

    @model_validator(mode="after")
    def validate_accounts(self) -> "TransactionRecord":
        if self.type == TransactionType.TRANSFER:
            if not self.account_from or not self.account_to:
                raise ValueError("transfer requires both account_from and account_to")
        return self

    @model_validator(mode="after")
    def validate_non_transfer_account_to(self) -> "TransactionRecord":
        if self.type != TransactionType.TRANSFER and self.account_to:
            raise ValueError("account_to is only valid for transfer transactions")
        return self

    def to_row(self) -> list[str]:
        return [
            self.transaction_id,
            self.transaction_date.isoformat(),
            self.type.value,
            str(self.amount),
            self.subcategory,
            self.description,
            self.category,
            self.payment_method,
            self.account_to,
            self.merchant_or_source,
            self.input_mode.value,
            self.raw_input,
            f"{self.ai_confidence:.2f}",
            self.status.value,
        ]


class ParsedTransaction(BaseModel):
    type: TransactionType | None = None
    amount: int | None = None
    currency: str = "IDR"
    transaction_date: date = Field(default_factory=date.today)
    category: str = ""
    subcategory: str = ""
    account_from: str = ""
    account_to: str = ""
    merchant_or_source: str = ""
    description: str = ""
    payment_method: str = ""
    tags: list[str] = Field(default_factory=list)
    raw_input: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_confirmation: bool = False
    missing_fields: list[str] = Field(default_factory=list)

    def to_transaction_record(self, input_mode: InputMode) -> TransactionRecord:
        if self.type is None:
            raise ValueError("parsed transaction does not have a type")
        if self.amount is None:
            raise ValueError("parsed transaction does not have an amount")
        return TransactionRecord(
            type=self.type,
            amount=self.amount,
            currency=self.currency,
            transaction_date=self.transaction_date,
            category=self.category or "Other",
            subcategory=self.subcategory,
            account_from=self.payment_method or self.account_from,
            account_to=self.account_to,
            merchant_or_source=self.merchant_or_source,
            description=self.description,
            payment_method=self.payment_method or self.account_from,
            tags=self.tags,
            input_mode=input_mode,
            raw_input=self.raw_input,
            ai_confidence=self.confidence,
            status=TransactionStatus.PENDING if self.needs_confirmation else TransactionStatus.CONFIRMED,
        )


class BudgetRecord(BaseModel):
    month: str
    category_name: str
    budget_amount: int = Field(ge=0)


class MonthlyOverview(BaseModel):
    month: str
    total_income: int = 0
    total_expense: int = 0
    total_transfer: int = 0
    net_cash_flow: int = 0
    savings_rate: float = 0.0
    largest_expense_category: str = ""
    largest_income_source: str = ""


class CategorySummary(BaseModel):
    month: str
    category: str
    total_amount: int
    budget_amount: int = 0
    difference: int = 0
    percent_of_total_expense: float = 0.0


class IncomeSourceSummary(BaseModel):
    month: str
    source: str
    total_amount: int
    percent_of_total_income: float = 0.0


class AccountBalanceSummary(BaseModel):
    account_name: str
    opening_balance: int = 0
    inflow: int = 0
    outflow: int = 0
    closing_balance: int = 0


class ImprovementInsight(BaseModel):
    month: str
    insight_type: str
    insight_text: str
    priority: str


class MonthlySummary(BaseModel):
    overview: MonthlyOverview
    expense_categories: list[CategorySummary]
    income_sources: list[IncomeSourceSummary]
    account_balances: list[AccountBalanceSummary]
    insights: list[ImprovementInsight]


def sum_amounts(items: Iterable[TransactionRecord]) -> int:
    return sum(item.amount for item in items if item.status != TransactionStatus.DELETED)
