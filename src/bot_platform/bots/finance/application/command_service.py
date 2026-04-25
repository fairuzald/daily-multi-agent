from __future__ import annotations

from datetime import date, datetime

from bot_platform.bots.finance.domain.command_parser import ParsedCommand
from bot_platform.bots.finance.domain.policies import FinanceBotPolicy
from bot_platform.bots.finance.domain.responses import BotResponse, ReplyContextInput
from bot_platform.bots.finance.infrastructure.repositories import BudgetRule
from bot_platform.bots.finance.infrastructure.state_store import ReplyMessageContext
from bot_platform.bots.finance.models import TransactionStatus, TransactionType

from .guard_service import GuardService
from .transaction_persistence_service import TransactionPersistenceService
from .transaction_query_service import TransactionQueryService


class CommandService:
    def __init__(
        self,
        guards: GuardService,
        queries: TransactionQueryService,
        persistence: TransactionPersistenceService,
    ) -> None:
        self.guards = guards
        self.queries = queries
        self.persistence = persistence
        self.runtime = guards.runtime

    def _require_owner_with_sheet(self, user_id: int) -> BotResponse | None:
        return self.guards.ensure_owner_with_sheet(user_id)

    def handle_month_command(self, user_id: int, month: str | None = None) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        normalized_month = FinanceBotPolicy.normalize_month(month)
        transactions = self.queries.load_transactions()
        summary = self.runtime.summary_service.build_monthly_summary(month=normalized_month, transactions=transactions, budgets=[])
        self.persistence.replace_summary(summary)
        return BotResponse(
            self.runtime.summary_service.format_monthly_summary_message(summary),
            reply_context=ReplyMessageContext(kind="summary", month=normalized_month),
        )

    def handle_today_command(self, user_id: int, day: str | None = None) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        target_day = FinanceBotPolicy.normalize_day(day)
        transactions = [item for item in self.queries.load_transactions() if item.transaction_date == target_day]
        period_label = target_day.isoformat()
        summary = self.runtime.summary_service.build_period_summary(period_label=period_label, transactions=transactions, budgets=[])
        self.persistence.replace_summary(summary)
        return BotResponse(
            self.runtime.summary_service.format_monthly_summary_message(summary),
            reply_context=ReplyMessageContext(kind="summary", month=period_label),
        )

    def handle_week_command(self, user_id: int, week: str | None = None) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        week_start, week_end, label = FinanceBotPolicy.normalize_week(week)
        transactions = [item for item in self.queries.load_transactions() if week_start <= item.transaction_date <= week_end]
        summary = self.runtime.summary_service.build_period_summary(period_label=label, transactions=transactions, budgets=[])
        self.persistence.replace_summary(summary)
        return BotResponse(
            self.runtime.summary_service.format_monthly_summary_message(summary),
            reply_context=ReplyMessageContext(kind="summary", month=label),
        )

    def handle_delete_last_command(self, user_id: int, chat_id: int) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        return self._handle_delete_command(chat_id, reply_context=None)

    def handle_delete_reply_command(self, user_id: int, chat_id: int, reply_context: ReplyContextInput | None) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        return self._handle_delete_command(chat_id, reply_context=reply_context)

    def handle_edit_last_command(
        self,
        user_id: int,
        chat_id: int,
        correction_input: str,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        return self._handle_edit_command(chat_id, correction_input, reply_context=None, message_datetime=message_datetime)

    def handle_edit_reply_command(
        self,
        user_id: int,
        chat_id: int,
        correction_input: str,
        reply_context: ReplyContextInput | None,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        return self._handle_edit_command(chat_id, correction_input, reply_context=reply_context, message_datetime=message_datetime)

    def handle_read_strict_command(
        self,
        user_id: int,
        category: str,
        period: str,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        return self._handle_read_command(f"show {category} this {period}", message_datetime)

    def handle_budget_set_command(
        self,
        user_id: int,
        period: str,
        scope: str,
        amount: int,
        category: str = "",
    ) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        return self._handle_budget_set(
            ParsedCommand(intent="budget_set", period=period, target=scope, amount=amount, category=category)
        )

    def handle_budget_show_command(self, user_id: int, period: str, message_datetime: datetime | None = None) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        return self._handle_budget_show(ParsedCommand(intent="budget_show", period=period), message_datetime)

    def handle_compare_month_command(self, user_id: int, message_datetime: datetime | None = None) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error
        return self._handle_compare_month(message_datetime)

    def handle_command(
        self,
        chat_id: int,
        message_text: str,
        command: ParsedCommand,
        reply_context: ReplyContextInput | None,
        message_datetime: datetime | None,
    ) -> BotResponse:
        if command.intent == "delete":
            if command.target == "reply" and (reply_context is None or not reply_context.is_bot_reply):
                return BotResponse(
                    "Balas pesan transaksi yang mau dihapus, lalu tulis `hapus ini` supaya aku tahu transaksi mana yang dimaksud."
                )
            return self._handle_delete_command(chat_id, reply_context)
        if command.intent == "edit":
            if command.target == "reply" and (reply_context is None or not reply_context.is_bot_reply):
                return BotResponse(
                    "Balas pesan transaksi yang mau diubah, lalu tulis `ubah ini jadi ...` biar aku tahu transaksi mana yang harus diedit."
                )
            correction_text = command.correction_text.strip()
            if not correction_text:
                return BotResponse(
                    "Aku masih butuh detail perubahannya. Contohnya: `ubah ini jadi 35k pakai GoPay`, `ganti jadi makan siang 25rb`, atau `hapus ini`."
                )
            return self._handle_edit_command(chat_id, correction_text, reply_context, message_datetime)
        if command.intent == "read":
            return self._handle_read_command(message_text, message_datetime)
        if command.intent == "budget_set":
            return self._handle_budget_set(command)
        if command.intent == "budget_show":
            return self._handle_budget_show(command, message_datetime)
        if command.intent == "summary":
            return self._handle_natural_summary(command, message_datetime)
        if command.intent == "compare_month":
            return self._handle_compare_month(message_datetime)
        return BotResponse("Aku belum benar-benar paham maksudnya. Coba tulis lebih spesifik, misalnya transaksi baru, ubah transaksi, hapus, atau minta ringkasan.")

    def _handle_delete_command(self, chat_id: int, reply_context: ReplyContextInput | None) -> BotResponse:
        transaction = self.queries.resolve_transaction_target(chat_id, reply_context)
        if transaction is None:
            return BotResponse(
                "Aku belum ketemu transaksi yang mau dihapus. Coba balas pesan transaksi yang tersimpan, atau bilang kalau mau hapus transaksi terakhir."
            )
        deleted_record = transaction.model_copy(update={"status": TransactionStatus.DELETED})
        self.guards.sheets_client().update_transaction(deleted_record)
        self.runtime.state_store.set_transaction_snapshot(deleted_record)
        self.runtime.state_store.set_last_transaction_id(chat_id, deleted_record.transaction_id)
        return BotResponse(
            "Sudah kuhapus transaksi itu.",
            reply_context=ReplyMessageContext(kind="saved", transaction_id=deleted_record.transaction_id),
        )

    def _handle_edit_command(
        self,
        chat_id: int,
        correction_input: str,
        reply_context: ReplyContextInput | None,
        message_datetime: datetime | None,
    ) -> BotResponse:
        transaction = self.queries.resolve_transaction_target(chat_id, reply_context)
        if transaction is None:
            return BotResponse(
                "Aku belum ketemu transaksi yang mau diubah. Coba balas pesan transaksi yang tersimpan, atau bilang kalau mau ubah transaksi terakhir."
            )
        corrected = self.runtime.ai_client.correct_transaction(original=transaction, correction_input=correction_input)
        corrected = self.queries.apply_deterministic_enrichment(corrected, correction_input, message_datetime)
        corrected = FinanceBotPolicy.prepare_for_save(corrected)
        if corrected.confidence < self.runtime.low_confidence_threshold or corrected.missing_fields:
            self.runtime.state_store.set_pending(chat_id, corrected, transaction.input_mode)
            return FinanceBotPolicy.format_confirmation_message(corrected, source_label="reply update")
        updated_record = corrected.to_transaction_record(input_mode=transaction.input_mode).model_copy(
            update={"transaction_id": transaction.transaction_id, "status": TransactionStatus.EDITED}
        )
        self.persistence.update_transaction(updated_record)
        amount = f"Rp{updated_record.amount:,}".replace(",", ".")
        return BotResponse(
            "\n".join(
                [
                    "Sudah kuubah transaksi ini:",
                    f"- Jenis: {updated_record.type.value.replace('_', ' ')}",
                    f"- Nominal: {amount}",
                    f"- Kategori: {updated_record.category or '-'}",
                    f"- Subkategori: {updated_record.subcategory or '-'}",
                    f"- Metode: {updated_record.payment_method or updated_record.account_from or '-'}",
                    f"- Tanggal: {updated_record.transaction_date.isoformat()}",
                    f"- Catatan: {updated_record.description or '-'}",
                ]
            ),
            reply_context=ReplyMessageContext(kind="saved", transaction_id=updated_record.transaction_id),
        )

    def _handle_read_command(self, message_text: str, message_datetime: datetime | None) -> BotResponse:
        transactions = self.queries.filter_transactions(message_text, message_datetime)
        if not transactions:
            return BotResponse("Aku belum nemu transaksi yang cocok dengan permintaan itu.")
        lines = ["Ini transaksi yang ketemu:"]
        for item in transactions[:10]:
            amount = f"Rp{item.amount:,}".replace(",", ".")
            lines.append(
                f"- {item.transaction_date.isoformat()} {item.category}/{item.subcategory or '-'} {amount} via {item.payment_method or item.account_from or '-'} ({item.status.value})"
            )
        if len(transactions) > 10:
            lines.append(f"...dan masih ada {len(transactions) - 10} transaksi lagi.")
        return BotResponse("\n".join(lines))

    def _handle_budget_set(self, command: ParsedCommand) -> BotResponse:
        if command.amount is None or command.amount <= 0:
            return BotResponse("Nominal budgetnya belum jelas. Contoh: `set monthly food budget 500000`.")
        rule = BudgetRule(
            scope=command.target or ("category" if command.category else "global"),
            period=command.period or "monthly",
            category=command.category,
            limit_amount=command.amount,
        )
        self.runtime.finance_repository.save_budget_rule(rule)
        label = f"{rule.period} {rule.scope}"
        if rule.category:
            label += f" for {rule.category}"
        return BotResponse(f"Budget {label} sudah kusimpan: Rp{rule.limit_amount:,}".replace(",", "."))

    def _handle_budget_show(self, command: ParsedCommand, message_datetime: datetime | None) -> BotResponse:
        transactions = self.queries.filter_transactions(command.period or "month", message_datetime)
        rules = self.runtime.finance_repository.list_budget_rules()
        if not rules:
            return BotResponse("Belum ada budget yang tersimpan.")
        total_expense = sum(
            item.amount
            for item in transactions
            if item.type in {TransactionType.EXPENSE, TransactionType.INVESTMENT_OUT} and item.status != TransactionStatus.DELETED
        )
        lines = ["Status budget saat ini:"]
        for rule in rules:
            if rule.scope == "global":
                used = total_expense
            else:
                used = sum(
                    item.amount
                    for item in transactions
                    if item.category.lower() == rule.category.lower() and item.status != TransactionStatus.DELETED
                )
            remaining = rule.limit_amount - used
            status = "Melebihi budget" if remaining < 0 else "Masih aman"
            lines.append(
                f"- {rule.period} {rule.scope} {rule.category or 'semua'}: terpakai Rp{used:,}, sisa Rp{remaining:,} [{status}]".replace(
                    ",", "."
                )
            )
        return BotResponse("\n".join(lines))

    def _handle_compare_month(self, message_datetime: datetime | None) -> BotResponse:
        reference_day = self.runtime.date_parser.reference_date(message_datetime)
        current_month = reference_day.strftime("%Y-%m")
        previous_month = (reference_day.replace(day=1) - date.resolution).strftime("%Y-%m")
        transactions = self.queries.load_transactions()
        comparison = self.runtime.summary_service.compare_months(
            current_month=current_month,
            previous_month=previous_month,
            transactions=transactions,
        )
        return BotResponse(comparison)

    def _handle_natural_summary(self, command: ParsedCommand, message_datetime: datetime | None) -> BotResponse:
        period = command.period or "month"
        reference_day = self.runtime.date_parser.reference_date(message_datetime)
        if period == "today":
            target_day = FinanceBotPolicy.normalize_day(reference_day.isoformat())
            transactions = [item for item in self.queries.load_transactions() if item.transaction_date == target_day]
            period_label = target_day.isoformat()
            summary = self.runtime.summary_service.build_period_summary(period_label=period_label, transactions=transactions, budgets=[])
            self.persistence.replace_summary(summary)
            return BotResponse(
                self.runtime.summary_service.format_monthly_summary_message(summary),
                reply_context=ReplyMessageContext(kind="summary", month=period_label),
            )
        if period == "week":
            week_start, week_end, label = FinanceBotPolicy.normalize_week(reference_day.isoformat())
            transactions = [item for item in self.queries.load_transactions() if week_start <= item.transaction_date <= week_end]
            summary = self.runtime.summary_service.build_period_summary(period_label=label, transactions=transactions, budgets=[])
            self.persistence.replace_summary(summary)
            return BotResponse(
                self.runtime.summary_service.format_monthly_summary_message(summary),
                reply_context=ReplyMessageContext(kind="summary", month=label),
            )
        normalized_month = FinanceBotPolicy.normalize_month(reference_day.strftime("%Y-%m"))
        transactions = self.queries.load_transactions()
        summary = self.runtime.summary_service.build_monthly_summary(month=normalized_month, transactions=transactions, budgets=[])
        self.persistence.replace_summary(summary)
        return BotResponse(
            self.runtime.summary_service.format_monthly_summary_message(summary),
            reply_context=ReplyMessageContext(kind="summary", month=normalized_month),
        )
