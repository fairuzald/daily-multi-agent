from __future__ import annotations

from datetime import date, datetime

from bot_platform.bots.finance.categories import DEFAULT_CATEGORIES
from bot_platform.bots.finance.domain.policies import FinanceBotPolicy
from bot_platform.bots.finance.domain.responses import ReplyContextInput
from bot_platform.bots.finance.models import ParsedTransaction, TransactionRecord, TransactionStatus, TransactionType

from .guard_service import GuardService


class TransactionQueryService:
    def __init__(self, guards: GuardService) -> None:
        self.guards = guards
        self.runtime = guards.runtime

    def apply_deterministic_enrichment(
        self,
        parsed: ParsedTransaction,
        raw_text: str,
        message_datetime: datetime | None,
    ) -> ParsedTransaction:
        date_resolution = self.runtime.date_parser.resolve(raw_text, message_datetime=message_datetime)
        if date_resolution.ambiguous:
            payload = parsed.model_dump()
            missing_fields = list(payload.get("missing_fields", []))
            if "transaction_date" not in missing_fields:
                missing_fields.append("transaction_date")
            payload.update({"needs_confirmation": True, "missing_fields": missing_fields})
            return ParsedTransaction.model_validate(payload)

        payload = parsed.model_dump()
        payload["transaction_date"] = date_resolution.resolved_date

        for mapping in self.runtime.finance_repository.list_learned_mappings():
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

    def load_transactions(self) -> list[TransactionRecord]:
        records: list[TransactionRecord] = []
        current_transaction_date = ""
        current_group_id = ""
        group_shared_values: dict[str, str] = {}
        for row in self.guards.sheets_client().read_transactions():
            if not row:
                continue
            group_id = str(row.get("Transaction Group ID") or "").strip()
            if group_id and group_id != current_group_id:
                current_group_id = group_id
                group_shared_values = {}

            row_transaction_date = str(row.get("Transaction Date") or "").strip()
            if row_transaction_date:
                current_transaction_date = row_transaction_date
            if not current_transaction_date:
                continue

            resolved_row = dict(row)
            if group_id:
                for key in (
                    "Type",
                    "Amount",
                    "Description",
                    "Category",
                    "Payment Method",
                    "Destination Account / Wallet",
                    "Merchant / Source",
                    "Input Mode",
                    "Raw Input",
                    "AI Confidence",
                    "Status",
                    "Group Total Amount",
                ):
                    value = str(resolved_row.get(key) or "").strip()
                    if value:
                        group_shared_values[key] = value
                    elif key in group_shared_values:
                        resolved_row[key] = group_shared_values[key]

            transaction_type = FinanceBotPolicy.normalize_transaction_type(resolved_row)
            amount_value = FinanceBotPolicy.parse_row_amount(resolved_row)
            if transaction_type is None or amount_value is None:
                continue

            input_mode, raw_input, ai_confidence, status = FinanceBotPolicy.normalize_transaction_runtime_fields(resolved_row)
            account_to = str(resolved_row.get("Destination Account / Wallet") or "").strip()
            if transaction_type != TransactionType.TRANSFER:
                account_to = ""
            try:
                records.append(
                    TransactionRecord(
                        transaction_id=str(resolved_row.get("Transaction ID") or ""),
                        transaction_date=current_transaction_date,
                        type=transaction_type,
                        amount=amount_value,
                        category=str(resolved_row.get("Category") or "Other"),
                        subcategory=str(resolved_row.get("Subcategory") or ""),
                        account_from=str(resolved_row.get("Payment Method") or resolved_row.get("Account / Wallet") or ""),
                        account_to=account_to,
                        merchant_or_source=str(resolved_row.get("Merchant / Source") or ""),
                        description=str(resolved_row.get("Description") or ""),
                        payment_method=str(resolved_row.get("Payment Method") or resolved_row.get("Account / Wallet") or ""),
                        input_mode=input_mode,
                        raw_input=raw_input,
                        ai_confidence=ai_confidence,
                        status=status,
                        group_id=group_id,
                        group_total_amount=int("".join(ch for ch in str(resolved_row.get("Group Total Amount") or "") if ch.isdigit()))
                        if str(resolved_row.get("Group Total Amount") or "").strip()
                        else None,
                    )
                )
            except Exception:
                continue
        return records

    def resolve_transaction_target(
        self,
        chat_id: int,
        reply_context: ReplyContextInput | None,
    ) -> TransactionRecord | None:
        matched_reply_context = self.guards.matched_reply_context(chat_id, reply_context)
        if matched_reply_context and matched_reply_context.transaction_id:
            return self.runtime.state_store.get_transaction_snapshot(matched_reply_context.transaction_id)
        last_transaction_id = self.runtime.state_store.get_last_transaction_id(chat_id)
        if not last_transaction_id:
            return None
        return self.runtime.state_store.get_transaction_snapshot(last_transaction_id)

    def filter_transactions(self, query_text: str, message_datetime: datetime | None) -> list[TransactionRecord]:
        lowered = query_text.lower()
        transactions = [item for item in self.load_transactions() if item.status != TransactionStatus.DELETED]
        reference_day = self.runtime.date_parser.reference_date(message_datetime)

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
        for mapping in self.runtime.finance_repository.list_learned_mappings():
            if mapping.category and mapping.pattern.lower() in lowered:
                return mapping.category
        return ""
