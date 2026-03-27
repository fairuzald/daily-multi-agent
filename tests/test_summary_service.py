from datetime import date

from bot_platform.bots.finance.models import BudgetRecord, TransactionRecord
from bot_platform.bots.finance.domain.summary_service import SummaryService


def test_build_monthly_summary_rolls_up_totals_and_insights() -> None:
    transactions = [
        TransactionRecord(
            transaction_date=date(2026, 3, 1),
            type="income",
            amount=8_000_000,
            category="Salary",
            account_from="BCA",
            merchant_or_source="Salary",
        ),
        TransactionRecord(
            transaction_date=date(2026, 3, 2),
            type="expense",
            amount=2_100_000,
            category="Food",
            account_from="BCA",
            merchant_or_source="Food Hall",
        ),
        TransactionRecord(
            transaction_date=date(2026, 3, 3),
            type="expense",
            amount=1_200_000,
            category="Transport",
            account_from="BCA",
            merchant_or_source="Shell",
        ),
        TransactionRecord(
            transaction_date=date(2026, 3, 4),
            type="expense",
            amount=186_000,
            category="Entertainment",
            account_from="BCA",
            merchant_or_source="Netflix",
        ),
        TransactionRecord(
            transaction_date=date(2026, 3, 12),
            type="expense",
            amount=186_000,
            category="Entertainment",
            account_from="BCA",
            merchant_or_source="Netflix",
        ),
    ]
    budgets = [
        BudgetRecord(month="2026-03", category_name="Food", budget_amount=2_000_000),
        BudgetRecord(month="2026-03", category_name="Transport", budget_amount=1_500_000),
    ]

    summary = SummaryService().build_monthly_summary("2026-03", transactions, budgets)

    assert summary.overview.total_income == 8_000_000
    assert summary.overview.total_expense == 3_672_000
    assert summary.overview.largest_expense_category == "Food"
    assert summary.expense_categories[0].difference == -100_000
    assert any(item.insight_type == "overspending" for item in summary.insights)
    assert any(item.insight_type == "subscription" for item in summary.insights)


def test_format_monthly_summary_message_is_human_readable() -> None:
    transactions = [
        TransactionRecord(
            transaction_date=date(2026, 3, 1),
            type="income",
            amount=5_000_000,
            category="Salary",
            account_from="BCA",
            merchant_or_source="Salary",
        ),
        TransactionRecord(
            transaction_date=date(2026, 3, 3),
            type="expense",
            amount=1_000_000,
            category="Food",
            account_from="BCA",
        ),
    ]
    summary = SummaryService().build_monthly_summary("2026-03", transactions, [])

    message = SummaryService().format_monthly_summary_message(summary)

    assert "Summary for 2026-03" in message
    assert "Income: Rp5.000.000" in message
    assert "Expenses: Rp1.000.000" in message
    assert "Transfers: Rp0" in message


def test_build_monthly_summary_treats_investment_flows_as_cash_movement() -> None:
    transactions = [
        TransactionRecord(
            transaction_date=date(2026, 3, 1),
            type="investment_in",
            amount=2_000_000,
            category="Investment",
            account_from="BCA",
            merchant_or_source="Mutual Fund",
        ),
        TransactionRecord(
            transaction_date=date(2026, 3, 3),
            type="investment_out",
            amount=500_000,
            category="Investment",
            account_from="BCA",
            merchant_or_source="Stocks",
        ),
    ]

    summary = SummaryService().build_monthly_summary("2026-03", transactions, [])

    assert summary.overview.total_income == 2_000_000
    assert summary.overview.total_expense == 500_000
    assert summary.overview.total_transfer == 0
    assert summary.overview.net_cash_flow == 1_500_000


def test_build_monthly_summary_handles_transfer_only_month_without_fake_savings_warning() -> None:
    transactions = [
        TransactionRecord(
            transaction_date=date(2026, 3, 10),
            type="transfer",
            amount=200_000,
            category="Transfer",
            subcategory="Internal Transfer",
            payment_method="BCA",
            account_from="BCA",
            account_to="Dewa's Account",
            merchant_or_source="Transfer",
        ),
    ]

    summary = SummaryService().build_monthly_summary("2026-03", transactions, [])
    message = SummaryService().format_monthly_summary_message(summary)

    assert summary.overview.total_income == 0
    assert summary.overview.total_expense == 0
    assert summary.overview.total_transfer == 200_000
    assert summary.overview.net_cash_flow == 0
    assert all(item.insight_type != "savings_rate" for item in summary.insights)
    assert any(item.insight_type == "transfer_activity" for item in summary.insights)
    assert "Transfers: Rp200.000" in message
    assert "No expense transactions in this period." in message
