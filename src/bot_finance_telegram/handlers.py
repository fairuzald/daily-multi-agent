from __future__ import annotations

from datetime import date
import re
from dataclasses import dataclass

from bot_finance_telegram.categories import DEFAULT_CATEGORIES, DEFAULT_WALLETS
from bot_finance_telegram.models import InputMode, ParsedTransaction, TransactionRecord, TransactionStatus
from bot_finance_telegram.services.sheets_client import build_category_rows
from bot_finance_telegram.services.state_store import BotStateStore, PendingTransactionState, ReplyMessageContext
from bot_finance_telegram.services.summary_service import SummaryService


class BotResponse(str):
    def __new__(cls, text: str, reply_context: ReplyMessageContext | None = None):
        obj = str.__new__(cls, text)
        obj.reply_context = reply_context
        return obj


@dataclass
class ReplyContextInput:
    message_id: int | None = None
    is_bot_reply: bool = False


class BotHandlers:
    def __init__(
        self,
        gemini_client,
        sheets_client_factory,
        summary_service: SummaryService,
        state_store: BotStateStore,
        low_confidence_threshold: float = 0.8,
        service_account_email: str = "",
    ) -> None:
        self.gemini_client = gemini_client
        self.sheets_client_factory = sheets_client_factory
        self.summary_service = summary_service
        self.state_store = state_store
        self.low_confidence_threshold = low_confidence_threshold
        self.service_account_email = service_account_email

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
            f"Active sheet is configured.\n"
            f"Use /help to see commands and input examples."
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
            "/month [MM-YYYY|YYYY-MM] - generate a summary for any month\n"
            "/whoami - show your Telegram user ID\n\n"
            "How to use:\n"
            "- Send a Google Sheets link after /start or /set_sheet\n"
            "- Send transactions in plain text, for example:\n"
            "  beli kopi 25000 pakai bca\n"
            "  gaji masuk 8000000 ke bri\n"
            "  transfer 500000 dari BCA ke GoPay\n\n"
            "- Send a voice note in Indonesian for hands-free logging\n"
            "- Send a receipt, bill photo, or payment screenshot to extract one transaction\n\n"
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

        matched_reply_context = self._matched_reply_context(reply_context)
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
        return self._handle_parsed_transaction(chat_id=chat_id, parsed=parsed, input_mode=InputMode.TEXT)

    def handle_voice_transcript(
        self,
        user_id: int,
        chat_id: int,
        transcript: str,
        reply_context: ReplyContextInput | None = None,
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        matched_reply_context = self._matched_reply_context(reply_context)
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
        return self._handle_parsed_transaction(chat_id=chat_id, parsed=parsed, input_mode=InputMode.VOICE)

    def handle_image_message(
        self,
        user_id: int,
        chat_id: int,
        parsed: ParsedTransaction,
        reply_context: ReplyContextInput | None = None,
    ) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        matched_reply_context = self._matched_reply_context(reply_context)
        pending = self.state_store.get_pending(chat_id)
        if pending is not None and (matched_reply_context is None or matched_reply_context.kind == "confirmation"):
            return self._handle_pending_confirmation(chat_id, parsed.raw_input, pending)
        if pending is None and matched_reply_context and matched_reply_context.kind == "confirmation":
            return BotResponse(
                "That confirmation context has expired. Please resend the transaction or reply to a newer bot message."
            )
        if matched_reply_context and matched_reply_context.kind == "saved":
            return self._handle_saved_reply(chat_id, parsed.raw_input, matched_reply_context)
        return self._handle_parsed_transaction(chat_id=chat_id, parsed=parsed, input_mode=InputMode.IMAGE)

    def handle_month_command(self, user_id: int, month: str | None = None) -> BotResponse:
        if not self._is_authorized(user_id):
            return BotResponse(self._unauthorized_message())
        if not self.state_store.get_active_sheet_id():
            return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")
        month = self._normalize_month(month)
        transactions = self._load_transactions()
        summary = self.summary_service.build_monthly_summary(month=month, transactions=transactions, budgets=[])
        self._sheets_client().replace_summary(summary)
        return BotResponse(
            self.summary_service.format_monthly_summary_message(summary),
            reply_context=ReplyMessageContext(kind="summary", month=month),
        )

    def _load_transactions(self) -> list[TransactionRecord]:
        records = []
        current_transaction_date = ""
        for row in self._sheets_client().read_transactions():
            if not row:
                continue
            row_transaction_date = str(row.get("Transaction Date") or "").strip()
            if row_transaction_date:
                current_transaction_date = row_transaction_date
            if not current_transaction_date:
                continue
            transaction_type = str(row.get("Type") or "").strip()
            amount_value = str(row.get("Amount") or "").strip()
            if not transaction_type or not amount_value:
                continue
            records.append(
                TransactionRecord(
                    transaction_id=str(row.get("Transaction ID") or ""),
                    transaction_date=current_transaction_date,
                    type=transaction_type,
                    amount=int(float(amount_value or 0)),
                    category=str(row.get("Category") or "Other"),
                    subcategory=str(row.get("Subcategory") or ""),
                    account_from=str(row.get("Payment Method") or row.get("Account / Wallet") or ""),
                    account_to=str(row.get("Destination Account / Wallet") or ""),
                    merchant_or_source=str(row.get("Merchant / Source") or ""),
                    description=str(row.get("Description") or ""),
                    payment_method=str(row.get("Payment Method") or row.get("Account / Wallet") or ""),
                    input_mode=row.get("Input Mode") or "text",
                    raw_input=str(row.get("Raw Input") or ""),
                    ai_confidence=float(row.get("AI Confidence") or 1.0),
                    status=row.get("Status") or "confirmed",
                )
            )
        return records

    def _format_saved_message(self, transaction: TransactionRecord) -> BotResponse:
        amount = f"Rp{transaction.amount:,}".replace(",", ".")
        return BotResponse(
            f"Saved: {transaction.type.value.title()} {amount}, "
            f"{transaction.category}, {transaction.payment_method or transaction.account_from or '-'}, "
            f"{transaction.merchant_or_source or '-'}",
            reply_context=ReplyMessageContext(kind="saved", transaction_id=transaction.transaction_id),
        )

    def _format_confirmation_message(self, parsed: ParsedTransaction, source_label: str = "message") -> BotResponse:
        amount = f"Rp{parsed.amount:,}".replace(",", ".") if parsed.amount else "-"
        summary = (
            f"Type: {self._transaction_type_label(parsed.type)}\n"
            f"Amount: {amount}\n"
            f"Date: {parsed.transaction_date.isoformat()}\n"
            f"Category: {parsed.category or '-'}\n"
            f"Payment method: {parsed.payment_method or parsed.account_from or '-'}\n"
            f"Destination: {parsed.account_to or '-'}\n"
            f"Merchant/source: {parsed.merchant_or_source or '-'}\n"
            f"Description: {parsed.description or '-'}"
        )
        if parsed.missing_fields:
            missing = ", ".join(parsed.missing_fields)
            return BotResponse(
                f"I parsed this {source_label}, but I need confirmation before saving.\n\n"
                f"{summary}\n\n"
                f"Still missing or uncertain: {missing}\n"
                "Reply with the missing value, or reply 'yes' to save as-is if the summary already looks correct.",
                reply_context=ReplyMessageContext(kind="confirmation"),
            )
        return BotResponse(
            f"I parsed this {source_label}, but confidence is still low.\n\n"
            f"{summary}\n\n"
            "Reply 'yes' to save, or send a correction message.",
            reply_context=ReplyMessageContext(kind="confirmation"),
        )

    def _handle_pending_confirmation(self, chat_id: int, message_text: str, pending: PendingTransactionState) -> BotResponse:
        parsed = pending.parsed
        normalized = message_text.strip().lower()
        if normalized in {"yes", "y", "ok", "oke", "correct", "confirm", "save"}:
            if parsed.missing_fields:
                return self._format_confirmation_message(parsed)
            return self._save_pending(chat_id, parsed, pending.input_mode)

        updated = self._apply_follow_up_answer(parsed, message_text)
        if not updated.missing_fields:
            return self._save_pending(chat_id, updated, pending.input_mode)

        self.state_store.set_pending(chat_id, updated, pending.input_mode)
        return self._format_confirmation_message(updated)

    def _apply_follow_up_answer(self, parsed: ParsedTransaction, message_text: str) -> ParsedTransaction:
        if not parsed.missing_fields:
            return parsed

        field_name = parsed.missing_fields[0]
        value = message_text.strip()
        parsed_value = self._parse_follow_up_value(field_name, value)
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
        finalized = self._prepare_for_save(parsed)
        if finalized.missing_fields:
            self.state_store.set_pending(chat_id, finalized, input_mode)
            return self._format_confirmation_message(finalized, source_label=self._source_label(input_mode))
        transaction = finalized.to_transaction_record(input_mode=input_mode)
        self._sheets_client().append_transaction(transaction)
        self.state_store.clear_pending(chat_id)
        self.state_store.set_last_transaction_id(chat_id, transaction.transaction_id)
        self.state_store.set_transaction_snapshot(transaction)
        return self._format_saved_message(transaction)

    def _handle_parsed_transaction(self, chat_id: int, parsed: ParsedTransaction, input_mode: InputMode) -> BotResponse:
        parsed = self._prepare_for_save(parsed)
        if parsed.confidence < self.low_confidence_threshold or parsed.missing_fields:
            self.state_store.set_pending(chat_id, parsed, input_mode)
            return self._format_confirmation_message(parsed, source_label=self._source_label(input_mode))

        transaction = parsed.to_transaction_record(input_mode=input_mode)
        self._sheets_client().append_transaction(transaction)
        self.state_store.set_last_transaction_id(chat_id, transaction.transaction_id)
        self.state_store.set_transaction_snapshot(transaction)
        return self._format_saved_message(transaction)

    def _handle_saved_reply(self, chat_id: int, message_text: str, reply_context: ReplyMessageContext) -> BotResponse:
        original = self.state_store.get_transaction_snapshot(reply_context.transaction_id)
        if original is None:
            return BotResponse(
                "I could not find the original transaction behind that reply anymore. "
                "Please resend the corrected transaction as a new message."
            )
        corrected = self.gemini_client.correct_transaction(original=original, correction_input=message_text)
        corrected = self._prepare_for_save(corrected)
        if corrected.confidence < self.low_confidence_threshold or corrected.missing_fields:
            self.state_store.set_pending(chat_id, corrected, original.input_mode)
            return self._format_confirmation_message(corrected, source_label="reply update")

        updated_record = corrected.to_transaction_record(input_mode=original.input_mode).model_copy(
            update={"transaction_id": original.transaction_id, "status": TransactionStatus.EDITED}
        )
        self._sheets_client().update_transaction(updated_record)
        self.state_store.set_transaction_snapshot(updated_record)
        return BotResponse(
            f"Updated: {updated_record.type.value.title()} Rp{updated_record.amount:,}".replace(",", "."),
            reply_context=ReplyMessageContext(kind="saved", transaction_id=updated_record.transaction_id),
        )

    def _prepare_for_save(self, parsed: ParsedTransaction) -> ParsedTransaction:
        missing_fields = list(parsed.missing_fields)
        updates: dict[str, object] = {}

        if parsed.type != "transfer" and parsed.account_to:
            updates["account_to"] = ""

        payment_method = (parsed.payment_method or parsed.account_from or "").strip()
        updates["payment_method"] = payment_method
        updates["account_from"] = payment_method

        if parsed.amount is None or parsed.amount <= 0:
            updates["amount"] = None
            if "amount" not in missing_fields:
                missing_fields.append("amount")

        if parsed.type is None and "type" not in missing_fields:
            missing_fields.insert(0, "type")

        required_fields = ["type", "amount", "subcategory", "description", "payment_method"]
        if parsed.type == "transfer":
            required_fields.append("account_to")
        for field_name in required_fields:
            current_value = updates.get(field_name, getattr(parsed, field_name, ""))
            if current_value in (None, "") and field_name not in missing_fields:
                missing_fields.append(field_name)

        updates["missing_fields"] = missing_fields
        updates["needs_confirmation"] = bool(missing_fields)
        return parsed.model_copy(update=updates)

    @staticmethod
    def _source_label(input_mode: InputMode) -> str:
        source_label_map = {
            InputMode.TEXT: "message",
            InputMode.VOICE: "voice note",
            InputMode.IMAGE: "image",
        }
        return source_label_map[input_mode]

    @staticmethod
    def _transaction_type_label(value) -> str:
        if value is None:
            return "-"
        return getattr(value, "value", str(value))

    def _parse_follow_up_value(self, field_name: str, value: str):
        normalized = value.strip().lower()
        if field_name == "type":
            type_map = {
                "expense": "expense",
                "pengeluaran": "expense",
                "income": "income",
                "pemasukan": "income",
                "transfer": "transfer",
                "investment in": "investment_in",
                "investment_in": "investment_in",
                "investasi masuk": "investment_in",
                "investment out": "investment_out",
                "investment_out": "investment_out",
                "investasi keluar": "investment_out",
            }
            return type_map.get(normalized)
        if field_name == "amount":
            digits = "".join(ch for ch in value if ch.isdigit())
            return int(digits) if digits else None
        if field_name in {"payment_method", "description", "subcategory", "account_to"}:
            return value.strip()
        return None

    def _claim_or_authorize_owner(self, user_id: int) -> bool:
        owner = self.state_store.get_owner_user_id()
        if owner is None:
            self.state_store.set_owner_user_id(user_id)
            return True
        return owner == user_id

    def _is_authorized(self, user_id: int) -> bool:
        owner = self.state_store.get_owner_user_id()
        return owner is not None and owner == user_id

    def _unauthorized_message(self) -> str:
        return "You are not authorized to use this bot."

    def _sheets_client(self):
        sheet_id = self.state_store.get_active_sheet_id()
        if not sheet_id:
            raise RuntimeError("No active sheet configured")
        return self.sheets_client_factory(sheet_id)

    def _configure_sheet_from_link(self, message_text: str) -> BotResponse:
        sheet_id = self._extract_sheet_id(message_text)
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

    @staticmethod
    def _normalize_month(month: str | None) -> str:
        if not month:
            return date.today().strftime("%Y-%m")
        value = month.strip()
        if re.fullmatch(r"\d{4}-\d{2}", value):
            year, month_number = value.split("-", maxsplit=1)
            if 1 <= int(month_number) <= 12:
                return f"{year}-{month_number}"
        if re.fullmatch(r"\d{2}-\d{4}", value):
            month_number, year = value.split("-", maxsplit=1)
            if 1 <= int(month_number) <= 12:
                return f"{year}-{month_number}"
        raise ValueError("Invalid month format. Use /month, /month 2026-03, or /month 03-2026.")

    def _matched_reply_context(self, reply_context: ReplyContextInput | None) -> ReplyMessageContext | None:
        if reply_context is None or not reply_context.is_bot_reply:
            return None
        return self.state_store.get_reply_context(reply_context.message_id)

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

    @staticmethod
    def _extract_sheet_id(link: str) -> str:
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", link)
        return match.group(1) if match else ""
