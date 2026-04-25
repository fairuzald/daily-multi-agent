from __future__ import annotations

import re
from datetime import date, timedelta

from bot_platform.bots.finance.domain.amounts import parse_amount_expression
from bot_platform.bots.finance.domain.inference_catalog import load_inference_catalog
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
        lines = [
            "Sudah kusimpan:",
            f"- Jenis: {transaction.type.value.replace('_', ' ')}",
            f"- Nominal: {amount}",
            f"- Kategori: {transaction.category or '-'}",
            f"- Subkategori: {transaction.subcategory or '-'}",
            f"- Metode: {transaction.payment_method or transaction.account_from or '-'}",
            f"- Tanggal: {transaction.transaction_date.isoformat()}",
        ]
        if transaction.merchant_or_source:
            lines.append(f"- Merchant/sumber: {transaction.merchant_or_source}")
        if transaction.description:
            lines.append(f"- Catatan: {transaction.description}")
        return BotResponse("\n".join(lines), reply_context=ReplyMessageContext(kind="saved", transaction_id=transaction.transaction_id))

    @staticmethod
    def format_group_saved_message(transactions: list[TransactionRecord], *, forced_even_split: bool = False) -> BotResponse:
        if forced_even_split and transactions and transactions[0].group_total_amount:
            total_amount = transactions[0].group_total_amount or 0
        else:
            total_amount = sum(item.amount for item in transactions)
        total_label = f"Rp{total_amount:,}".replace(",", ".")
        if forced_even_split and transactions and transactions[0].group_total_amount:
            lines = [f"Sudah kusimpan {len(transactions)} transaksi dalam satu grup. Total gabungan: {total_label}."]
        else:
            lines = [f"Sudah kusimpan {len(transactions)} transaksi dalam satu grup. Total: {total_label}."]
        for item in transactions:
            if forced_even_split and item.group_total_amount:
                lines.append(f"- {item.subcategory or item.description or item.category}")
            else:
                amount = f"Rp{item.amount:,}".replace(",", ".")
                lines.append(f"- {item.subcategory or item.description or item.category}: {amount}")
        if forced_even_split:
            lines.append("Aku pakai total gabungan yang sama karena pembagian nominal per item belum jelas.")
        return BotResponse(
            "\n".join(lines),
            reply_context=ReplyMessageContext(kind="saved", transaction_id=transactions[-1].transaction_id),
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
            missing = ", ".join(cls.humanize_missing_field(item) for item in parsed.missing_fields)
            return BotResponse(
                f"Aku masih belum yakin dengan {source_label} ini, jadi aku belum simpan dulu.\n\n"
                f"{summary}\n\n"
                f"Bagian yang masih kurang jelas: {missing}\n"
                "Balas dengan info yang kurang, atau balas `ya` kalau ringkasan ini sudah benar.",
                reply_context=ReplyMessageContext(kind="confirmation"),
            )
        return BotResponse(
            f"Aku sudah baca {source_label} ini, tapi masih ragu sedikit.\n\n"
            f"{summary}\n\n"
            "Kalau sudah benar, balas `ya`. Kalau belum, balas dengan koreksinya pakai bahasa biasa.",
            reply_context=ReplyMessageContext(kind="confirmation"),
        )

    @staticmethod
    def format_group_confirmation_message(item_labels: list[str], shared_total_amount: int, source_label: str) -> BotResponse:
        total_label = f"Rp{shared_total_amount:,}".replace(",", ".")
        lines = [
            f"Aku nangkep ada beberapa item di {source_label} ini, tapi totalnya masih gabung: {total_label}.",
            "",
            "Daftar item yang terbaca:",
        ]
        for label in item_labels:
            lines.append(f"- {label}")
        lines.extend(
            [
                "",
                "Balas dengan nominal tiap item sesuai urutan, atau balas `force` kalau mau tetap kusimpan dengan total gabungan.",
            ]
        )
        return BotResponse("\n".join(lines), reply_context=ReplyMessageContext(kind="confirmation"))

    @staticmethod
    def humanize_missing_field(field_name: str) -> str:
        mapping = {
            "type": "jenis transaksi",
            "amount": "nominal",
            "subcategory": "subkategori",
            "description": "catatan/deskripsi",
            "payment_method": "metode pembayaran",
            "account_to": "tujuan transfer",
            "transaction_date": "tanggal transaksi",
        }
        return mapping.get(field_name, field_name)

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
        catalog = load_inference_catalog()
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
                category = catalog.income.category_for(haystack) or merchant or catalog.income.default_category
            subcategory = subcategory or merchant or category or catalog.income.default_subcategory
            description = description or merchant or raw_input or catalog.income.default_description
            return category, subcategory, description

        if parsed.type == TransactionType.INVESTMENT_IN:
            category = category or catalog.investment_in.default_category
            subcategory = subcategory or merchant or catalog.investment_in.default_subcategory
            description = description or merchant or raw_input or catalog.investment_in.default_description
            return category, subcategory, description

        if parsed.type == TransactionType.INVESTMENT_OUT:
            category = category or catalog.investment_out.default_category
            subcategory = subcategory or merchant or catalog.investment_out.default_subcategory
            description = description or merchant or raw_input or catalog.investment_out.default_description
            return category, subcategory, description

        if not category or category.lower() == "other":
            category = catalog.expense.category_for(haystack) or merchant or catalog.expense.default_category

        subcategory = subcategory or merchant or cls.default_subcategory_for_category(category, parsed.type)
        description = description or merchant or raw_input or f"{category} {catalog.expense.default_description_suffix}".strip()
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
            return parse_amount_expression(value)
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
