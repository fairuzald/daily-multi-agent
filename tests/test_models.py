from datetime import date

import pytest

from bot_platform.bots.finance.models import InputMode, ParsedTransaction, TransactionRecord


def test_transfer_requires_both_accounts() -> None:
    with pytest.raises(ValueError):
        TransactionRecord(
            type="transfer",
            amount=100000,
            category="Transfer",
            account_from="BCA",
        )


def test_expense_defaults_currency_to_idr() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=25000,
        category="Food",
        raw_input="beli kopi 25 ribu",
        confidence=0.95,
    )

    record = parsed.to_transaction_record(input_mode=InputMode.TEXT)

    assert record.currency == "IDR"
    assert record.status == "confirmed"


def test_parsed_transaction_preserves_date() -> None:
    parsed = ParsedTransaction(
        type="income",
        amount=1000000,
        category="Salary",
        raw_input="gaji masuk",
        confidence=0.99,
        transaction_date=date(2026, 3, 1),
    )

    record = parsed.to_transaction_record(input_mode=InputMode.TEXT)

    assert record.transaction_date == date(2026, 3, 1)

