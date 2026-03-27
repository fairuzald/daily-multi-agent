from __future__ import annotations

from datetime import date, datetime

from bot_platform.bots.finance.categories import DEFAULT_CATEGORIES, DEFAULT_WALLETS
from bot_platform.bots.finance.domain.command_parser import CommandParser, ParsedCommand
from bot_platform.bots.finance.domain.date_parser import DateParser
from bot_platform.bots.finance.domain.policies import FinanceBotPolicy
from bot_platform.bots.finance.domain.responses import BotResponse, ReplyContextInput
from bot_platform.bots.finance.domain.summary_service import SummaryService
from bot_platform.bots.finance.infrastructure.repositories import BudgetRule, FinanceRepository, LearnedMapping
from bot_platform.bots.finance.infrastructure.sheets_gateway import build_category_rows
from bot_platform.bots.finance.infrastructure.state_store import BotStateStore, PendingTransactionState, ReplyMessageContext
from bot_platform.bots.finance.models import InputMode, ParsedTransaction, TransactionRecord, TransactionStatus, TransactionType


class FinanceBotService:
    def __init__(
        self,
        gemini_client,
        sheets_client_factory,
        summary_service: SummaryService,
        state_store: BotStateStore,
        finance_repository: FinanceRepository,
        low_confidence_threshold: float = 0.8,
        service_account_email: str = "",
        default_timezone: str = "Asia/Jakarta",
    ) -> None:
        self.gemini_client = gemini_client
        self.sheets_client_factory = sheets_client_factory
        self.summary_service = summary_service
        self.state_store = state_store
        self.finance_repository = finance_repository
        self.low_confidence_threshold = low_confidence_threshold
        self.service_account_email = service_account_email
        self.date_parser = DateParser(default_timezone)
        self.command_parser = CommandParser()

    def handle_start(self, user_id: int) -> BotResponse:
        if not self._claim_or_authorize_owner(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            self.state_store.set_awaiting_sheet_link(True)
            return BotResponse(
                "Owner verified. Send me your Google Sheets link and I will configure the sheet for you.\n\n"
                f"Share the sheet with this service account as Editor: {self.service_account_email}"
            )
        return BotResponse(
            "Finance bot is running.\n\n"
            "Active sheet is configured.\n"
            "Use /help to see commands and input examples."
        )

    def handle_help(self, user_id: int) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        return BotResponse(
            "Available commands:\n"
            "/start - claim or initialize the bot\n"
            "/help - show commands and examples\n"
            "/status - show owner and sheet setup status\n"
            "/set_sheet - ask for a Google Sheets link\n"
            "/add_payment_method - add a payment method like GoPay or BCA\n"
            "/add_categories - add a category/subcategory row\n"
            "/today [YYYY-MM-DD] - generate a summary for a day\n"
            "/week [YYYY-MM-DD|YYYY-Www] - generate a summary for a week\n"
            "/month [MM-YYYY|YYYY-MM] - generate a summary for a month (`/moth` also works)\n"
            "/delete_last - delete the latest saved transaction\n"
            "/delete_reply - delete the transaction behind the replied bot message\n"
            "/edit_last <amount> [payment_method] - update the latest saved transaction\n"
            "/edit_reply <amount> [payment_method] - update the replied transaction\n"
            "/read <category> <today|week|month> - strict transaction query\n"
            "/budget_set <weekly|monthly> <global|category> <amount> [category] - save a budget rule\n"
            "/budget_show <weekly|monthly> - show active budget usage\n"
            "/compare_month - compare this month against the previous month\n"
            "/whoami - show your Telegram user ID\n\n"
            "Natural commands:\n"
            "- `delete last` or reply `delete this`\n"
            "- `edit last 25000 pakai gopay`\n"
            "- `show food this week`\n"
            "- `compare month`\n"
            "- `set monthly food budget 500000`\n"
            "- `show budget this month`\n\n"
            "How to use:\n"
            "- Send a Google Sheets link after /start or /set_sheet\n"
            "- Send transactions in plain text, for example:\n"
            "  beli kopi 25000 pakai bca\n"
            "  makan siang 45000 kemarin pakai gopay\n"
            "  gaji masuk 8000000 ke bri\n"
            "  transfer 500000 dari BCA ke GoPay\n\n"
            "- Send a voice note in Indonesian for hands-free logging\n"
            "- Send a receipt, bill photo, or payment screenshot to extract one transaction\n\n"
            "Accuracy behavior:\n"
            "- Dates like `today`, `kemarin`, `2 hari lalu`, and `2026-03-27` are resolved in code\n"
            "- Ambiguous transactions stay in review instead of auto-saving\n"
            "- Merchant/category learning is reused before asking AI again\n\n"
            "Config commands:\n"
            "- /add_payment_method or /add-payment-method then send one value like `GoPay`\n"
            "- /add_categories or /add-categories then send `expense, Food, Dessert`\n\n"
            f"For sheet setup, share your sheet with this service account as Editor:\n{self.service_account_email}"
        )

    def handle_status(self, user_id: int) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        owner = self.state_store.get_owner_user_id()
        active_sheet = self.state_store.get_active_sheet_id() or "-"
        awaiting = "yes" if self.state_store.is_awaiting_sheet_link() else "no"
        return BotResponse(
            f"Owner Telegram user ID: {owner}\n"
            f"Active sheet ID: {active_sheet}\n"
            f"Awaiting sheet link: {awaiting}\n"
            f"Service account email: {self.service_account_email}"
        )

    def handle_whoami(self, user_id: int) -> BotResponse:
        owner = self.state_store.get_owner_user_id()
        status = "authorized owner" if owner == user_id else "not authorized"
        return BotResponse(f"Your Telegram user ID: {user_id}\nStatus: {status}")

    def handle_set_sheet(self, user_id: int) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        self.state_store.set_awaiting_sheet_link(True)
        return BotResponse(
            "Send me the full Google Sheets link.\n\n"
            f"Before that, share the sheet with this service account as Editor:\n{self.service_account_email}"
        )

    def handle_add_payment_method(self, user_id: int, chat_id: int) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        self.state_store.set_setup_mode(chat_id, "add_payment_method")
        return BotResponse(
            "Send one payment method name, for example: GoPay\n\n"
            f"Current defaults: {', '.join(DEFAULT_WALLETS)}"
        )

    def handle_add_categories(self, user_id: int, chat_id: int) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        self.state_store.set_setup_mode(chat_id, "add_categories")
        return BotResponse("Send `type, category, subcategory`, for example: expense, Food, Dessert")

    def handle_text_message(
        self,
        user_id: int,
        chat_id: int,
        message_text: str,
        reply_context: ReplyContextInput | None = None,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        if not self._claim_or_authorize_owner(user_id):
            return BotResponse(self._unauthorized_message())
        if self.state_store.is_awaiting_sheet_link():
            return self._configure_sheet_from_link(message_text)
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        setup_mode = self.state_store.get_setup_mode(chat_id)
        if setup_mode:
            return self._handle_setup_mode(chat_id, message_text, setup_mode)

        parsed_command = self.command_parser.parse(message_text)
        if parsed_command.intent:
            return self._handle_command(chat_id, message_text, parsed_command, reply_context, message_datetime)

        matched_reply_context = self._matched_reply_context(chat_id, reply_context)
        pending = self.state_store.get_pending(chat_id)
        if pending is not None and (matched_reply_context is None or matched_reply_context.kind == "confirmation"):
            return self._handle_pending_confirmation(chat_id, message_text, pending)
        if pending is None and matched_reply_context and matched_reply_context.kind == "confirmation":
            return BotResponse(
                "That confirmation context has expired. Please resend the transaction or reply to a newer bot message."
            )
        if matched_reply_context and matched_reply_context.kind == "saved":
            return self._handle_saved_reply(chat_id, message_text, matched_reply_context)
        if matched_reply_context and matched_reply_context.kind == "summary":
            return BotResponse(
                "Replying to a summary does not edit transactions directly. "
                "Reply to a saved transaction message to correct it, or use /month MM-YYYY for another month."
            )

        parsed = self.gemini_client.parse_transaction(message_text)
        parsed = self._apply_deterministic_enrichment(parsed, message_text, message_datetime)
        return self._handle_parsed_transaction(chat_id=chat_id, parsed=parsed, input_mode=InputMode.TEXT)

    def handle_voice_transcript(
        self,
        user_id: int,
        chat_id: int,
        transcript: str,
        reply_context: ReplyContextInput | None = None,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        matched_reply_context = self._matched_reply_context(chat_id, reply_context)
        pending = self.state_store.get_pending(chat_id)
        if pending is not None and (matched_reply_context is None or matched_reply_context.kind == "confirmation"):
            return self._handle_pending_confirmation(chat_id, transcript, pending)
        if pending is None and matched_reply_context and matched_reply_context.kind == "confirmation":
            return BotResponse(
                "That confirmation context has expired. Please resend the transaction or reply to a newer bot message."
            )
        if matched_reply_context and matched_reply_context.kind == "saved":
            return self._handle_saved_reply(chat_id, transcript, matched_reply_context)
        parsed = self.gemini_client.parse_transaction(transcript)
        parsed = self._apply_deterministic_enrichment(parsed, transcript, message_datetime)
        return self._handle_parsed_transaction(chat_id=chat_id, parsed=parsed, input_mode=InputMode.VOICE)

    def handle_image_message(
        self,
        user_id: int,
        chat_id: int,
        parsed: ParsedTransaction,
        reply_context: ReplyContextInput | None = None,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        matched_reply_context = self._matched_reply_context(chat_id, reply_context)
        pending = self.state_store.get_pending(chat_id)
        if pending is not None and (matched_reply_context is None or matched_reply_context.kind == "confirmation"):
            return self._handle_pending_confirmation(chat_id, parsed.raw_input, pending)
        if pending is None and matched_reply_context and matched_reply_context.kind == "confirmation":
            return BotResponse(
                "That confirmation context has expired. Please resend the transaction or reply to a newer bot message."
            )
        if matched_reply_context and matched_reply_context.kind == "saved":
            return self._handle_saved_reply(chat_id, parsed.raw_input, matched_reply_context)
        parsed = self._apply_deterministic_enrichment(parsed, parsed.raw_input, message_datetime)
        return self._handle_parsed_transaction(chat_id=chat_id, parsed=parsed, input_mode=InputMode.IMAGE)

    def handle_month_command(self, user_id: int, month: str | None = None) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        normalized_month = FinanceBotPolicy.normalize_month(month)
        transactions = self._load_transactions()
        summary = self.summary_service.build_monthly_summary(month=normalized_month, transactions=transactions, budgets=[])
        self._sheets_client().replace_summary(summary)
        return BotResponse(
            self.summary_service.format_monthly_summary_message(summary),
            reply_context=ReplyMessageContext(kind="summary", month=normalized_month),
        )

    def handle_today_command(self, user_id: int, day: str | None = None) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        target_day = FinanceBotPolicy.normalize_day(day)
        transactions = [item for item in self._load_transactions() if item.transaction_date == target_day]
        period_label = target_day.isoformat()
        summary = self.summary_service.build_period_summary(period_label=period_label, transactions=transactions, budgets=[])
        self._sheets_client().replace_summary(summary)
        return BotResponse(
            self.summary_service.format_monthly_summary_message(summary),
            reply_context=ReplyMessageContext(kind="summary", month=period_label),
        )

    def handle_week_command(self, user_id: int, week: str | None = None) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        week_start, week_end, label = FinanceBotPolicy.normalize_week(week)
        transactions = [item for item in self._load_transactions() if week_start <= item.transaction_date <= week_end]
        summary = self.summary_service.build_period_summary(period_label=label, transactions=transactions, budgets=[])
        self._sheets_client().replace_summary(summary)
        return BotResponse(
            self.summary_service.format_monthly_summary_message(summary),
            reply_context=ReplyMessageContext(kind="summary", month=label),
        )

    def handle_delete_last_command(self, user_id: int, chat_id: int) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        return self._handle_delete_command(chat_id, reply_context=None)

    def handle_delete_reply_command(
        self,
        user_id: int,
        chat_id: int,
        reply_context: ReplyContextInput | None,
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        return self._handle_delete_command(chat_id, reply_context=reply_context)

    def handle_edit_last_command(
        self,
        user_id: int,
        chat_id: int,
        correction_input: str,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        return self._handle_edit_command(
            chat_id=chat_id,
            message_text=correction_input,
            reply_context=None,
            message_datetime=message_datetime,
        )

    def handle_edit_reply_command(
        self,
        user_id: int,
        chat_id: int,
        correction_input: str,
        reply_context: ReplyContextInput | None,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        return self._handle_edit_command(
            chat_id=chat_id,
            message_text=correction_input,
            reply_context=reply_context,
            message_datetime=message_datetime,
        )

    def handle_read_strict_command(
        self,
        user_id: int,
        category: str,
        period: str,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        return self._handle_read_command(
            message_text=f"show {category} this {period}",
            message_datetime=message_datetime,
        )

    def handle_budget_set_command(
        self,
        user_id: int,
        period: str,
        scope: str,
        amount: int,
        category: str = "",
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        return self._handle_budget_set(
            ParsedCommand(
                intent="budget_set",
                period=period,
                target=scope,
                amount=amount,
                category=category,
            )
        )

    def handle_budget_show_command(
        self,
        user_id: int,
        period: str,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        return self._handle_budget_show(
            ParsedCommand(intent="budget_show", period=period),
            message_datetime=message_datetime,
        )

    def handle_compare_month_command(
        self,
        user_id: int,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        return self._handle_compare_month(message_datetime=message_datetime)

    def _load_transactions(self) -> list[TransactionRecord]:
        records: list[TransactionRecord] = []
        current_transaction_date = ""
        for row in self._sheets_client().read_transactions():
            if not row:
                continue
            row_transaction_date = str(row.get("Transaction Date") or "").strip()
            if row_transaction_date:
                current_transaction_date = row_transaction_date
            if not current_transaction_date:
                continue
            transaction_type = FinanceBotPolicy.normalize_transaction_type(row)
            amount_value = FinanceBotPolicy.parse_row_amount(row)
            if transaction_type is None or amount_value is None:
                continue
            input_mode, raw_input, ai_confidence, status = FinanceBotPolicy.normalize_transaction_runtime_fields(row)
            account_to = str(row.get("Destination Account / Wallet") or "").strip()
            if transaction_type != TransactionType.TRANSFER:
                account_to = ""
            try:
                records.append(
                    TransactionRecord(
                        transaction_id=str(row.get("Transaction ID") or ""),
                        transaction_date=current_transaction_date,
                        type=transaction_type,
                        amount=amount_value,
                        category=str(row.get("Category") or "Other"),
                        subcategory=str(row.get("Subcategory") or ""),
                        account_from=str(row.get("Payment Method") or row.get("Account / Wallet") or ""),
                        account_to=account_to,
                        merchant_or_source=str(row.get("Merchant / Source") or ""),
                        description=str(row.get("Description") or ""),
                        payment_method=str(row.get("Payment Method") or row.get("Account / Wallet") or ""),
                        input_mode=input_mode,
                        raw_input=raw_input,
                        ai_confidence=ai_confidence,
                        status=status,
                    )
                )
            except Exception:
                continue
        return records

    def _handle_pending_confirmation(self, chat_id: int, message_text: str, pending: PendingTransactionState) -> BotResponse:
        parsed = pending.parsed
        normalized = message_text.strip().lower()
        if normalized in {"yes", "y", "ok", "oke", "correct", "confirm", "save"}:
            return self._force_save_pending(chat_id, parsed, pending.input_mode)

        updated = self._apply_follow_up_answer(parsed, message_text)
        if not updated.missing_fields:
            return self._save_pending(chat_id, updated, pending.input_mode)

        self.state_store.set_pending(chat_id, updated, pending.input_mode)
        return FinanceBotPolicy.format_confirmation_message(updated)

    def _apply_follow_up_answer(self, parsed: ParsedTransaction, message_text: str) -> ParsedTransaction:
        if not parsed.missing_fields:
            return parsed

        field_name = parsed.missing_fields[0]
        value = message_text.strip()
        parsed_value = FinanceBotPolicy.parse_follow_up_value(field_name, value)
        updates = {field_name: value, "needs_confirmation": False}
        if parsed_value is not None:
            updates[field_name] = parsed_value
        remaining = [item for item in parsed.missing_fields if item != field_name]
        updates["missing_fields"] = remaining
        if remaining:
            updates["needs_confirmation"] = True
        payload = parsed.model_dump()
        payload.update(updates)
        return ParsedTransaction.model_validate(payload)

    def _save_pending(self, chat_id: int, parsed: ParsedTransaction, input_mode: InputMode) -> BotResponse:
        finalized = FinanceBotPolicy.prepare_for_save(parsed)
        if finalized.missing_fields:
            self.state_store.set_pending(chat_id, finalized, input_mode)
            return FinanceBotPolicy.format_confirmation_message(finalized, source_label=FinanceBotPolicy.source_label(input_mode))
        transaction = finalized.to_transaction_record(input_mode=input_mode)
        self._sheets_client().append_transaction(transaction)
        self.state_store.clear_pending(chat_id)
        self.state_store.set_last_transaction_id(chat_id, transaction.transaction_id)
        self.state_store.set_transaction_snapshot(transaction)
        self._learn_mapping_from_transaction(transaction)
        return FinanceBotPolicy.format_saved_message(transaction)

    def _force_save_pending(self, chat_id: int, parsed: ParsedTransaction, input_mode: InputMode) -> BotResponse:
        payment_method = (parsed.payment_method or parsed.account_from or "").strip()
        forced_payload = parsed.model_dump()
        forced_payload.update(
            {
                "payment_method": payment_method,
                "account_from": payment_method,
                "account_to": "" if parsed.type != "transfer" else parsed.account_to,
                "missing_fields": [],
                "needs_confirmation": False,
            }
        )
        forced = ParsedTransaction.model_validate(forced_payload)
        try:
            transaction = forced.to_transaction_record(input_mode=input_mode)
        except ValueError:
            blocking_fields: list[str] = []
            if forced.type is None:
                blocking_fields.append("type")
            if forced.amount is None or forced.amount <= 0:
                blocking_fields.append("amount")
            if forced.type == "transfer" and not forced.account_to:
                blocking_fields.append("account_to")
            restored = forced.model_copy(
                update={
                    "missing_fields": blocking_fields or list(parsed.missing_fields),
                    "needs_confirmation": True,
                }
            )
            self.state_store.set_pending(chat_id, restored, input_mode)
            if blocking_fields:
                return BotResponse(
                    "I still cannot save this as-is because core fields are missing: "
                    + ", ".join(blocking_fields)
                    + ". Reply with the missing value."
                )
            return FinanceBotPolicy.format_confirmation_message(
                restored,
                source_label=FinanceBotPolicy.source_label(input_mode),
            )

        self._sheets_client().append_transaction(transaction)
        self.state_store.clear_pending(chat_id)
        self.state_store.set_last_transaction_id(chat_id, transaction.transaction_id)
        self.state_store.set_transaction_snapshot(transaction)
        self._learn_mapping_from_transaction(transaction)
        return FinanceBotPolicy.format_saved_message(transaction)

    def _handle_parsed_transaction(self, chat_id: int, parsed: ParsedTransaction, input_mode: InputMode) -> BotResponse:
        parsed = FinanceBotPolicy.prepare_for_save(parsed)
        if parsed.confidence < self.low_confidence_threshold or parsed.missing_fields:
            self.state_store.set_pending(chat_id, parsed, input_mode)
            return FinanceBotPolicy.format_confirmation_message(
                parsed,
                source_label=FinanceBotPolicy.source_label(input_mode),
            )

        transaction = parsed.to_transaction_record(input_mode=input_mode)
        self._sheets_client().append_transaction(transaction)
        self.state_store.set_last_transaction_id(chat_id, transaction.transaction_id)
        self.state_store.set_transaction_snapshot(transaction)
        self._learn_mapping_from_transaction(transaction)
        return FinanceBotPolicy.format_saved_message(transaction)

    def _handle_saved_reply(self, chat_id: int, message_text: str, reply_context: ReplyMessageContext) -> BotResponse:
        original = self.state_store.get_transaction_snapshot(reply_context.transaction_id)
        if original is None:
            return BotResponse(
                "I could not find the original transaction behind that reply anymore. "
                "Please resend the corrected transaction as a new message."
            )
        corrected = self.gemini_client.correct_transaction(original=original, correction_input=message_text)
        corrected = FinanceBotPolicy.prepare_for_save(corrected)
        if corrected.confidence < self.low_confidence_threshold or corrected.missing_fields:
            self.state_store.set_pending(chat_id, corrected, original.input_mode)
            return FinanceBotPolicy.format_confirmation_message(corrected, source_label="reply update")

        updated_record = corrected.to_transaction_record(input_mode=original.input_mode).model_copy(
            update={"transaction_id": original.transaction_id, "status": TransactionStatus.EDITED}
        )
        self._sheets_client().update_transaction(updated_record)
        self.state_store.set_transaction_snapshot(updated_record)
        self._learn_mapping_from_transaction(updated_record)
        return BotResponse(
            f"Updated: {updated_record.type.value.title()} Rp{updated_record.amount:,}".replace(",", "."),
            reply_context=ReplyMessageContext(kind="saved", transaction_id=updated_record.transaction_id),
        )

    def _handle_command(
        self,
        chat_id: int,
        message_text: str,
        command: ParsedCommand,
        reply_context: ReplyContextInput | None,
        message_datetime: datetime | None,
    ) -> BotResponse:
        if command.intent == "delete":
            return self._handle_delete_command(chat_id, reply_context)
        if command.intent == "edit":
            return self._handle_edit_command(chat_id, message_text, reply_context, message_datetime)
        if command.intent == "read":
            return self._handle_read_command(message_text, message_datetime)
        if command.intent == "budget_set":
            return self._handle_budget_set(command)
        if command.intent == "budget_show":
            return self._handle_budget_show(command, message_datetime)
        if command.intent == "compare_month":
            return self._handle_compare_month(message_datetime)
        return BotResponse("I could not understand that command.")

    def _handle_delete_command(self, chat_id: int, reply_context: ReplyContextInput | None) -> BotResponse:
        transaction = self._resolve_transaction_target(chat_id, reply_context)
        if transaction is None:
            return BotResponse("I could not find a transaction to delete. Reply to a saved message or delete the last one.")
        deleted_record = transaction.model_copy(update={"status": TransactionStatus.DELETED})
        self._sheets_client().update_transaction(deleted_record)
        self.state_store.set_transaction_snapshot(deleted_record)
        self.state_store.set_last_transaction_id(chat_id, deleted_record.transaction_id)
        return BotResponse(
            f"Deleted transaction {deleted_record.transaction_id}.",
            reply_context=ReplyMessageContext(kind="saved", transaction_id=deleted_record.transaction_id),
        )

    def _handle_edit_command(
        self,
        chat_id: int,
        message_text: str,
        reply_context: ReplyContextInput | None,
        message_datetime: datetime | None,
    ) -> BotResponse:
        transaction = self._resolve_transaction_target(chat_id, reply_context)
        if transaction is None:
            return BotResponse("I could not find a transaction to edit. Reply to a saved message or edit the last one.")
        correction_input = message_text.split(maxsplit=1)[1] if len(message_text.split(maxsplit=1)) > 1 else message_text
        corrected = self.gemini_client.correct_transaction(original=transaction, correction_input=correction_input)
        corrected = self._apply_deterministic_enrichment(corrected, correction_input, message_datetime)
        corrected = FinanceBotPolicy.prepare_for_save(corrected)
        if corrected.confidence < self.low_confidence_threshold or corrected.missing_fields:
            self.state_store.set_pending(chat_id, corrected, transaction.input_mode)
            return FinanceBotPolicy.format_confirmation_message(corrected, source_label="reply update")
        updated_record = corrected.to_transaction_record(input_mode=transaction.input_mode).model_copy(
            update={"transaction_id": transaction.transaction_id, "status": TransactionStatus.EDITED}
        )
        self._sheets_client().update_transaction(updated_record)
        self.state_store.set_transaction_snapshot(updated_record)
        self._learn_mapping_from_transaction(updated_record)
        return BotResponse(
            f"Updated: {updated_record.type.value.title()} Rp{updated_record.amount:,}".replace(",", "."),
            reply_context=ReplyMessageContext(kind="saved", transaction_id=updated_record.transaction_id),
        )

    def _handle_read_command(self, message_text: str, message_datetime: datetime | None) -> BotResponse:
        transactions = self._filter_transactions(message_text, message_datetime)
        if not transactions:
            return BotResponse("No transactions matched that query.")
        lines = ["Matched transactions:"]
        for item in transactions[:10]:
            amount = f"Rp{item.amount:,}".replace(",", ".")
            lines.append(
                f"- {item.transaction_date.isoformat()} {item.category}/{item.subcategory or '-'} {amount} via {item.payment_method or item.account_from or '-'} ({item.status.value})"
            )
        if len(transactions) > 10:
            lines.append(f"...and {len(transactions) - 10} more")
        return BotResponse("\n".join(lines))

    def _handle_budget_set(self, command: ParsedCommand) -> BotResponse:
        if command.amount is None or command.amount <= 0:
            return BotResponse("Budget amount is missing. Example: set monthly food budget 500000")
        rule = BudgetRule(
            scope=command.target or ("category" if command.category else "global"),
            period=command.period or "monthly",
            category=command.category,
            limit_amount=command.amount,
        )
        self.finance_repository.save_budget_rule(rule)
        label = f"{rule.period} {rule.scope}"
        if rule.category:
            label += f" for {rule.category}"
        return BotResponse(f"Saved {label} budget: Rp{rule.limit_amount:,}".replace(",", "."))

    def _handle_budget_show(self, command: ParsedCommand, message_datetime: datetime | None) -> BotResponse:
        transactions = self._filter_transactions(command.period or "month", message_datetime)
        rules = self.finance_repository.list_budget_rules()
        if not rules:
            return BotResponse("No budget rules set yet.")
        total_expense = sum(item.amount for item in transactions if item.type in {TransactionType.EXPENSE, TransactionType.INVESTMENT_OUT} and item.status != TransactionStatus.DELETED)
        lines = ["Budget status:"]
        for rule in rules:
            if rule.scope == "global":
                used = total_expense
            else:
                used = sum(item.amount for item in transactions if item.category.lower() == rule.category.lower() and item.status != TransactionStatus.DELETED)
            remaining = rule.limit_amount - used
            status = "OVER" if remaining < 0 else "OK"
            lines.append(
                f"- {rule.period} {rule.scope} {rule.category or 'all'}: used Rp{used:,}, remaining Rp{remaining:,} [{status}]".replace(",", ".")
            )
        return BotResponse("\n".join(lines))

    def _handle_compare_month(self, message_datetime: datetime | None) -> BotResponse:
        reference_day = self.date_parser.reference_date(message_datetime)
        current_month = reference_day.strftime("%Y-%m")
        previous_month_day = (reference_day.replace(day=1) - date.resolution)
        previous_month = previous_month_day.strftime("%Y-%m")
        transactions = self._load_transactions()
        comparison = self.summary_service.compare_months(current_month=current_month, previous_month=previous_month, transactions=transactions)
        return BotResponse(comparison)

    def _resolve_transaction_target(
        self,
        chat_id: int,
        reply_context: ReplyContextInput | None,
    ) -> TransactionRecord | None:
        matched_reply_context = self._matched_reply_context(chat_id, reply_context)
        if matched_reply_context and matched_reply_context.transaction_id:
            return self.state_store.get_transaction_snapshot(matched_reply_context.transaction_id)
        last_transaction_id = self.state_store.get_last_transaction_id(chat_id)
        if not last_transaction_id:
            return None
        return self.state_store.get_transaction_snapshot(last_transaction_id)

    def _filter_transactions(self, query_text: str, message_datetime: datetime | None) -> list[TransactionRecord]:
        lowered = query_text.lower()
        transactions = [item for item in self._load_transactions() if item.status != TransactionStatus.DELETED]
        reference_day = self.date_parser.reference_date(message_datetime)

        if "today" in lowered or "hari ini" in lowered:
            transactions = [item for item in transactions if item.transaction_date == reference_day]
        elif "week" in lowered or "minggu" in lowered:
            week_start = reference_day - date.resolution * reference_day.weekday()
            week_end = week_start + date.resolution * 6
            transactions = [item for item in transactions if week_start <= item.transaction_date <= week_end]
        elif "month" in lowered or "bulan" in lowered:
            month_label = reference_day.strftime("%Y-%m")
            transactions = [item for item in transactions if item.transaction_date.strftime("%Y-%m") == month_label]

        category = self._detect_category(lowered)
        if category:
            transactions = [item for item in transactions if item.category.lower() == category.lower()]
        return transactions

    def _detect_category(self, lowered: str) -> str:
        for groups in DEFAULT_CATEGORIES.values():
            for category in groups.keys():
                if category.lower() in lowered:
                    return category
        for mapping in self.finance_repository.list_learned_mappings():
            if mapping.category and mapping.pattern.lower() in lowered:
                return mapping.category
        return ""

    def _apply_deterministic_enrichment(
        self,
        parsed: ParsedTransaction,
        raw_text: str,
        message_datetime: datetime | None,
    ) -> ParsedTransaction:
        date_resolution = self.date_parser.resolve(raw_text, message_datetime=message_datetime)
        if date_resolution.ambiguous:
            payload = parsed.model_dump()
            missing_fields = list(payload.get("missing_fields", []))
            if "transaction_date" not in missing_fields:
                missing_fields.append("transaction_date")
            payload.update({"needs_confirmation": True, "missing_fields": missing_fields})
            return ParsedTransaction.model_validate(payload)

        payload = parsed.model_dump()
        payload["transaction_date"] = date_resolution.resolved_date

        for mapping in self.finance_repository.list_learned_mappings():
            if mapping.pattern.lower() not in raw_text.lower():
                continue
            if mapping.category:
                payload["category"] = mapping.category
            if mapping.subcategory:
                payload["subcategory"] = mapping.subcategory
            if mapping.payment_method and not payload.get("payment_method"):
                payload["payment_method"] = mapping.payment_method
                payload["account_from"] = mapping.payment_method
            break

        return ParsedTransaction.model_validate(payload)

    def _learn_mapping_from_transaction(self, transaction: TransactionRecord) -> None:
        pattern = (transaction.merchant_or_source or transaction.description or "").strip()
        if not pattern:
            return
        mapping = LearnedMapping(
            pattern=pattern,
            category=transaction.category,
            subcategory=transaction.subcategory,
            payment_method=transaction.payment_method or transaction.account_from,
            learned_from=transaction.transaction_id,
        )
        self.finance_repository.save_learned_mapping(mapping)

    def _claim_or_authorize_owner(self, user_id: int) -> bool:
        owner = self.state_store.get_owner_user_id()
        if owner is None:
            self.state_store.set_owner_user_id(user_id)
            return True
        return owner == user_id

    def _is_authorized(self, user_id: int) -> bool:
        owner = self.state_store.get_owner_user_id()
        return owner is not None and owner == user_id

    @staticmethod
    def _unauthorized_message() -> str:
        return "You are not authorized to use this bot."

    def _sheets_client(self):
        sheet_id = self.state_store.get_active_sheet_id()
        if not sheet_id:
            raise RuntimeError("No active sheet configured")
        return self.sheets_client_factory(sheet_id)

    def _configure_sheet_from_link(self, message_text: str) -> BotResponse:
        sheet_id = FinanceBotPolicy.extract_sheet_id(message_text)
        if not sheet_id:
            return BotResponse("That does not look like a valid Google Sheets link. Send the full spreadsheet URL.")
        client = self.sheets_client_factory(sheet_id)
        try:
            client.ensure_schema()
            client.ensure_default_categories(build_category_rows(DEFAULT_CATEGORIES))
            for payment_method in DEFAULT_WALLETS:
                client.add_payment_method(payment_method)
        except PermissionError:
            return BotResponse(
                "I could not access that sheet. Share it with the service account as Editor and send the link again.\n\n"
                f"Service account: {self.service_account_email}"
            )
        self.state_store.set_active_sheet_id(sheet_id)
        self.state_store.set_awaiting_sheet_link(False)
        return BotResponse("Sheet connected successfully. The bot is ready to save transactions.")

    def _matched_reply_context(self, chat_id: int, reply_context: ReplyContextInput | None) -> ReplyMessageContext | None:
        if reply_context is None or not reply_context.is_bot_reply:
            return None
        return self.state_store.get_reply_context(chat_id, reply_context.message_id)

    def _handle_setup_mode(self, chat_id: int, message_text: str, setup_mode: str) -> BotResponse:
        if setup_mode == "add_payment_method":
            payment_method = message_text.strip()
            if not payment_method:
                return BotResponse("Payment method cannot be empty. Send one value like GoPay.")
            self._sheets_client().add_payment_method(payment_method)
            self.state_store.clear_setup_mode(chat_id)
            return BotResponse(f"Payment method added: {payment_method}")

        if setup_mode == "add_categories":
            parts = [part.strip() for part in message_text.split(",")]
            if len(parts) != 3 or not all(parts):
                return BotResponse("Use `type, category, subcategory`, for example: expense, Food, Dessert")
            tx_type, category, subcategory = parts
            self._sheets_client().add_category(tx_type.lower(), category, subcategory)
            self.state_store.clear_setup_mode(chat_id)
            return BotResponse(f"Category added: {tx_type.lower()} / {category} / {subcategory}")

        self.state_store.clear_setup_mode(chat_id)
        return BotResponse("That setup mode expired. Please run the command again.")
