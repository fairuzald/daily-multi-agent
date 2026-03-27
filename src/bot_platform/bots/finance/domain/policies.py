from __future__ import annotations

import re
from datetime import date, timedelta

from bot_platform.bots.finance.domain.responses import BotResponse
from bot_platform.bots.finance.infrastructure.state_store import ReplyMessageContext
from bot_platform.bots.finance.models import InputMode, ParsedTransaction, TransactionRecord, TransactionType


class FinanceBotPolicy:
    @staticmethod
    def normalize_transaction_type(row: dict[str, object]) -> TransactionType | None:
        valid_types = {item.value: item for item in TransactionType}
        for key in ("Type", "Amount", "Subcategory", "Description"):
            value = str(row.get(key) or "").strip().lower()
            if value in valid_types:
                return valid_types[value]
        return None

    @staticmethod
    def parse_row_amount(row: dict[str, object]) -> int | None:
        for key in ("Amount", "Subcategory", "Description", "Category"):
            value = str(row.get(key) or "").strip()
            digits = "".join(char for char in value if char.isdigit())
            if not digits:
                continue
            try:
                amount = int(digits)
            except ValueError:
                continue
            if amount > 0:
                return amount
        return None

    @staticmethod
    def normalize_transaction_runtime_fields(row: dict[str, object]) -> tuple[str, str, float, str]:
        raw_input_mode = str(row.get("Input Mode") or "").strip()
        raw_raw_input = str(row.get("Raw Input") or "").strip()
        raw_confidence = str(row.get("AI Confidence") or "").strip()
        raw_status = str(row.get("Status") or "").strip().lower()

        valid_input_modes = {"text", "voice", "image"}
        input_mode = raw_input_mode.lower() if raw_input_mode.lower() in valid_input_modes else ""
        raw_input = raw_raw_input

        if not input_mode:
            if raw_input_mode:
                raw_input = raw_input_mode
            if raw_raw_input and not raw_confidence:
                raw_confidence = raw_raw_input
            input_mode = "text"

        if raw_confidence.lower() in {"confirmed", "edited", "deleted", "pending"}:
            if not raw_status:
                raw_status = raw_confidence.lower()
            raw_confidence = ""

        try:
            ai_confidence = float(raw_confidence) if raw_confidence else 1.0
        except ValueError:
            ai_confidence = 1.0

        status = raw_status if raw_status in {"confirmed", "edited", "deleted", "pending"} else "confirmed"
        return input_mode, raw_input, ai_confidence, status

    @staticmethod
    def format_saved_message(transaction: TransactionRecord) -> BotResponse:
        amount = f"Rp{transaction.amount:,}".replace(",", ".")
        return BotResponse(
            f"Saved: {transaction.type.value.title()} {amount}, "
            f"{transaction.category}, {transaction.payment_method or transaction.account_from or '-'}, "
            f"{transaction.merchant_or_source or '-'}",
            reply_context=ReplyMessageContext(kind="saved", transaction_id=transaction.transaction_id),
        )

    @classmethod
    def format_confirmation_message(cls, parsed: ParsedTransaction, source_label: str = "message") -> BotResponse:
        amount = f"Rp{parsed.amount:,}".replace(",", ".") if parsed.amount else "-"
        summary = (
            f"Type: {cls.transaction_type_label(parsed.type)}\n"
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

    @classmethod
    def prepare_for_save(cls, parsed: ParsedTransaction) -> ParsedTransaction:
        missing_fields = list(parsed.missing_fields)
        updates: dict[str, object] = {}

        if parsed.type != TransactionType.TRANSFER and parsed.account_to:
            updates["account_to"] = ""

        payment_method = (parsed.payment_method or parsed.account_from or "").strip()
        updates["payment_method"] = payment_method
        updates["account_from"] = payment_method

        inferred_category, inferred_subcategory, inferred_description = cls.infer_transaction_details(
            parsed.model_copy(update=updates)
        )
        updates["category"] = inferred_category
        updates["subcategory"] = inferred_subcategory
        updates["description"] = inferred_description

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

    @classmethod
    def infer_transaction_details(cls, parsed: ParsedTransaction) -> tuple[str, str, str]:
        category = (parsed.category or "").strip()
        subcategory = (parsed.subcategory or "").strip()
        description = (parsed.description or "").strip()
        merchant = (parsed.merchant_or_source or "").strip()
        raw_input = (parsed.raw_input or "").strip()
        haystack = " ".join(part for part in [merchant, description, raw_input] if part).lower()

        if parsed.type == TransactionType.TRANSFER:
            category = category or "Transfer"
            subcategory = subcategory or merchant or parsed.account_to or "Transfer"
            description = description or f"Transfer to {parsed.account_to or merchant or 'destination'}"
            return category, subcategory, description

        if parsed.type == TransactionType.INCOME:
            if not category:
                if any(keyword in haystack for keyword in ("gaji", "salary", "payroll")):
                    category = "Salary"
                elif any(keyword in haystack for keyword in ("refund", "cashback")):
                    category = "Refund"
                elif merchant:
                    category = merchant
                else:
                    category = "Income"
            subcategory = subcategory or merchant or category
            description = description or merchant or raw_input or "Income transaction"
            return category, subcategory, description

        if parsed.type == TransactionType.INVESTMENT_IN:
            category = category or "Investment In"
            subcategory = subcategory or merchant or "Investment Return"
            description = description or merchant or raw_input or "Investment cash in"
            return category, subcategory, description

        if parsed.type == TransactionType.INVESTMENT_OUT:
            category = category or "Investment Out"
            subcategory = subcategory or merchant or "Investment Purchase"
            description = description or merchant or raw_input or "Investment cash out"
            return category, subcategory, description

        if not category or category.lower() == "other":
            if any(keyword in haystack for keyword in ("kopi", "coffee", "cafe", "tomoro", "starbucks", "jabarano")):
                category = "Coffee"
            elif any(keyword in haystack for keyword in ("makan", "meal", "resto", "restaurant", "dine")):
                category = "Meals"
            elif any(keyword in haystack for keyword in ("snack", "cemilan")):
                category = "Snacks"
            elif any(keyword in haystack for keyword in ("pln", "listrik", "electricity", "token listrik")):
                category = "Electricity Bill"
            elif any(keyword in haystack for keyword in ("wifi", "internet", "indihome", "biznet")):
                category = "Internet"
            elif any(keyword in haystack for keyword in ("spotify", "netflix", "youtube premium", "subscription", "langganan")):
                category = "Subscription"
            elif any(keyword in haystack for keyword in ("transport", "grab", "gocar", "gojek", "bensin", "fuel", "parking", "parkir")):
                category = "Transport"
            elif "transfer" in haystack:
                category = "Transfer"
            elif merchant:
                category = merchant
            else:
                category = "General Expense"

        subcategory = subcategory or merchant or cls.default_subcategory_for_category(category, parsed.type)
        description = description or merchant or raw_input or f"{category} transaction"
        return category, subcategory, description

    @staticmethod
    def default_subcategory_for_category(category: str, transaction_type: TransactionType | None) -> str:
        if category:
            return category
        if transaction_type == TransactionType.TRANSFER:
            return "Transfer"
        if transaction_type == TransactionType.INCOME:
            return "Income"
        return "General"

    @staticmethod
    def source_label(input_mode: InputMode) -> str:
        source_label_map = {
            InputMode.TEXT: "message",
            InputMode.VOICE: "voice note",
            InputMode.IMAGE: "image",
        }
        return source_label_map[input_mode]

    @staticmethod
    def transaction_type_label(value: object) -> str:
        if value is None:
            return "-"
        return getattr(value, "value", str(value))

    @staticmethod
    def parse_follow_up_value(field_name: str, value: str):
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

    @staticmethod
    def normalize_month(month: str | None) -> str:
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

    @staticmethod
    def normalize_day(day: str | None) -> date:
        if not day:
            return date.today()
        value = day.strip()
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Invalid day format. Use /today or /today 2026-03-23.") from exc

    @staticmethod
    def normalize_week(week: str | None) -> tuple[date, date, str]:
        if not week:
            target_day = date.today()
        else:
            value = week.strip()
            if re.fullmatch(r"\d{4}-W\d{2}", value):
                year_text, week_text = value.split("-W", maxsplit=1)
                try:
                    target_day = date.fromisocalendar(int(year_text), int(week_text), 1)
                except ValueError as exc:
                    raise ValueError("Invalid week format. Use /week, /week 2026-03-23, or /week 2026-W13.") from exc
            else:
                try:
                    target_day = date.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError("Invalid week format. Use /week, /week 2026-03-23, or /week 2026-W13.") from exc
        week_start = target_day - timedelta(days=target_day.weekday())
        week_end = week_start + timedelta(days=6)
        iso_year, iso_week, _ = target_day.isocalendar()
        return week_start, week_end, f"{iso_year}-W{iso_week:02d}"

    @staticmethod
    def extract_sheet_id(link: str) -> str:
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", link)
        return match.group(1) if match else ""
