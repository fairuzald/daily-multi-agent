from __future__ import annotations

from collections import Counter, defaultdict

from bot_platform.bots.finance.models import (
    AccountBalanceSummary,
    BudgetRecord,
    CategorySummary,
    ImprovementInsight,
    IncomeSourceSummary,
    MonthlyOverview,
    MonthlySummary,
    TransactionRecord,
    TransactionStatus,
    TransactionType,
)


class SummaryService:
    def build_monthly_summary(
        self,
        month: str,
        transactions: list[TransactionRecord],
        budgets: list[BudgetRecord] | None = None,
    ) -> MonthlySummary:
        month_transactions = [
            item
            for item in transactions
            if item.status != TransactionStatus.DELETED and item.transaction_date.strftime("%Y-%m") == month
        ]
        return self.build_period_summary(month, month_transactions, budgets or [])

    def build_period_summary(
        self,
        period_label: str,
        transactions: list[TransactionRecord],
        budgets: list[BudgetRecord] | None = None,
    ) -> MonthlySummary:
        budgets = budgets or []

        counted_transactions = self._counted_transactions(transactions)
        income = [item for item in counted_transactions if item.type in {TransactionType.INCOME, TransactionType.INVESTMENT_IN}]
        expenses = [item for item in counted_transactions if item.type in {TransactionType.EXPENSE, TransactionType.INVESTMENT_OUT}]
        transfers = [item for item in counted_transactions if item.type == TransactionType.TRANSFER]

        total_income = sum(item.amount for item in income)
        total_expense = sum(item.amount for item in expenses)
        total_transfer = sum(item.amount for item in transfers)
        net_cash_flow = total_income - total_expense
        savings_rate = round((net_cash_flow / total_income), 4) if total_income else 0.0

        expense_totals = self._group_by_category(expenses)
        income_totals = self._group_by_source(income)

        overview = MonthlyOverview(
            month=period_label,
            total_income=total_income,
            total_expense=total_expense,
            total_transfer=total_transfer,
            net_cash_flow=net_cash_flow,
            savings_rate=savings_rate,
            largest_expense_category=max(expense_totals, key=expense_totals.get, default=""),
            largest_income_source=max(income_totals, key=income_totals.get, default=""),
        )

        budget_map = {item.category_name: item.budget_amount for item in budgets if item.month == period_label}
        expense_categories = []
        for category, total in sorted(expense_totals.items(), key=lambda pair: pair[1], reverse=True):
            budget_amount = budget_map.get(category, 0)
            difference = budget_amount - total
            share = round(total / total_expense, 4) if total_expense else 0.0
            expense_categories.append(
                CategorySummary(
                    month=period_label,
                    category=category,
                    total_amount=total,
                    budget_amount=budget_amount,
                    difference=difference,
                    percent_of_total_expense=share,
                )
            )

        income_sources = []
        for source, total in sorted(income_totals.items(), key=lambda pair: pair[1], reverse=True):
            income_sources.append(
                IncomeSourceSummary(
                    month=period_label,
                    source=source,
                    total_amount=total,
                    percent_of_total_income=round(total / total_income, 4) if total_income else 0.0,
                )
            )

        account_balances = self._build_account_balances(expenses, income, transfers)
        insights = self._build_insights(period_label, overview, expense_categories, counted_transactions)

        return MonthlySummary(
            overview=overview,
            expense_categories=expense_categories,
            income_sources=income_sources,
            account_balances=account_balances,
            insights=insights,
        )

    def format_monthly_summary_message(self, summary: MonthlySummary) -> str:
        overview = summary.overview
        lines = [
            f"Ringkasan keuangan untuk {overview.month}",
            "",
            f"- Pemasukan: Rp{overview.total_income:,}".replace(",", "."),
            f"- Pengeluaran: Rp{overview.total_expense:,}".replace(",", "."),
            f"- Transfer: Rp{overview.total_transfer:,}".replace(",", "."),
            f"- Arus kas bersih: Rp{overview.net_cash_flow:,}".replace(",", "."),
            f"- Rasio tabungan: {overview.savings_rate * 100:.1f}%",
            "",
            "Pengeluaran terbesar:",
        ]
        if summary.expense_categories:
            for index, item in enumerate(summary.expense_categories[:3], start=1):
                lines.append(f"{index}. {item.category}: Rp{item.total_amount:,}".replace(",", "."))
        else:
            lines.append("Belum ada pengeluaran di periode ini.")
        if summary.income_sources:
            lines.extend(["", "Sumber pemasukan utama:"])
            for index, item in enumerate(summary.income_sources[:3], start=1):
                lines.append(f"{index}. {item.source}: Rp{item.total_amount:,}".replace(",", "."))
        if summary.insights:
            lines.extend(["", "Catatan penting:"])
            for item in summary.insights[:3]:
                lines.append(f"- {item.insight_text}")
        return "\n".join(lines)

    def compare_months(self, current_month: str, previous_month: str, transactions: list[TransactionRecord]) -> str:
        current = self.build_monthly_summary(current_month, transactions, budgets=[])
        previous = self.build_monthly_summary(previous_month, transactions, budgets=[])
        income_delta = current.overview.total_income - previous.overview.total_income
        expense_delta = current.overview.total_expense - previous.overview.total_expense
        top_current = current.overview.largest_expense_category or "-"
        top_previous = previous.overview.largest_expense_category or "-"
        return "\n".join(
            [
                f"Perbandingan {current_month} vs {previous_month}",
                f"- Selisih pemasukan: Rp{income_delta:,}".replace(",", "."),
                f"- Selisih pengeluaran: Rp{expense_delta:,}".replace(",", "."),
                f"- Pengeluaran terbesar bulan ini: {top_current}",
                f"- Pengeluaran terbesar bulan sebelumnya: {top_previous}",
            ]
        )

    def _group_by_category(self, transactions: list[TransactionRecord]) -> dict[str, int]:
        totals: dict[str, int] = defaultdict(int)
        for item in transactions:
            totals[item.category or "Other"] += item.amount
        return dict(totals)

    def _group_by_source(self, transactions: list[TransactionRecord]) -> dict[str, int]:
        totals: dict[str, int] = defaultdict(int)
        for item in transactions:
            key = item.merchant_or_source or item.category or "Other"
            totals[key] += item.amount
        return dict(totals)

    def _counted_transactions(self, transactions: list[TransactionRecord]) -> list[TransactionRecord]:
        counted: list[TransactionRecord] = []
        seen_group_totals: set[str] = set()
        for item in transactions:
            if item.status == TransactionStatus.DELETED:
                continue
            if item.group_id and item.group_total_amount:
                if item.group_id in seen_group_totals:
                    counted.append(item.model_copy(update={"amount": 0}))
                    continue
                seen_group_totals.add(item.group_id)
                counted.append(item.model_copy(update={"amount": item.group_total_amount}))
                continue
            counted.append(item)
        return counted

    def _build_account_balances(
        self,
        expenses: list[TransactionRecord],
        income: list[TransactionRecord],
        transfers: list[TransactionRecord],
    ) -> list[AccountBalanceSummary]:
        inflow: dict[str, int] = defaultdict(int)
        outflow: dict[str, int] = defaultdict(int)
        accounts: set[str] = set()

        for item in expenses:
            if item.account_from:
                outflow[item.account_from] += item.amount
                accounts.add(item.account_from)
        for item in income:
            if item.account_from:
                inflow[item.account_from] += item.amount
                accounts.add(item.account_from)
        for item in transfers:
            if item.account_from:
                outflow[item.account_from] += item.amount
                accounts.add(item.account_from)
            if item.account_to:
                inflow[item.account_to] += item.amount
                accounts.add(item.account_to)

        summaries = []
        for account in sorted(accounts):
            incoming = inflow.get(account, 0)
            outgoing = outflow.get(account, 0)
            summaries.append(
                AccountBalanceSummary(
                    account_name=account,
                    opening_balance=0,
                    inflow=incoming,
                    outflow=outgoing,
                    closing_balance=incoming - outgoing,
                )
            )
        return summaries

    def _build_insights(
        self,
        month: str,
        overview: MonthlyOverview,
        category_summaries: list[CategorySummary],
        transactions: list[TransactionRecord],
    ) -> list[ImprovementInsight]:
        insights: list[ImprovementInsight] = []

        for item in category_summaries:
            if item.budget_amount and item.total_amount > item.budget_amount:
                delta = item.total_amount - item.budget_amount
                insights.append(
                    ImprovementInsight(
                        month=month,
                        insight_type="overspending",
                        insight_text=f"{item.category} spending is Rp{delta:,} above budget".replace(",", "."),
                        priority="high",
                    )
                )

        if category_summaries and category_summaries[0].percent_of_total_expense >= 0.4:
            top = category_summaries[0]
            insights.append(
                ImprovementInsight(
                    month=month,
                    insight_type="concentration",
                    insight_text=f"{top.category} makes up {top.percent_of_total_expense * 100:.0f}% of expenses",
                    priority="medium",
                )
            )

        if overview.total_income > 0 and overview.savings_rate < 0.1:
            insights.append(
                ImprovementInsight(
                    month=month,
                    insight_type="savings_rate",
                    insight_text="Savings rate is below 10%; consider tightening optional spending.",
                    priority="high",
                )
            )

        transfer_total = sum(item.amount for item in transactions if item.type == TransactionType.TRANSFER)
        if transfer_total > 0:
            insights.append(
                ImprovementInsight(
                    month=month,
                    insight_type="transfer_activity",
                    insight_text=f"Transfer movement in this period: Rp{transfer_total:,}".replace(",", "."),
                    priority="low",
                )
            )

        recurring_counter = Counter(
            item.merchant_or_source
            for item in transactions
            if item.type == TransactionType.EXPENSE and item.merchant_or_source
        )
        recurring_names = [name for name, count in recurring_counter.items() if count >= 2]
        if recurring_names:
            insights.append(
                ImprovementInsight(
                    month=month,
                    insight_type="subscription",
                    insight_text=f"Recurring expenses detected: {', '.join(sorted(recurring_names)[:3])}",
                    priority="medium",
                )
            )

        if not insights:
            insights.append(
                ImprovementInsight(
                    month=month,
                    insight_type="positive",
                    insight_text="Spending pattern looks stable in this period.",
                    priority="low",
                )
            )
        return insights
