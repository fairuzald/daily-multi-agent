from __future__ import annotations

from datetime import datetime

from bot_platform.bots.finance.domain.multi_transaction import parse_group_allocation_reply
from bot_platform.bots.finance.domain.policies import FinanceBotPolicy
from bot_platform.bots.finance.domain.responses import BotResponse
from bot_platform.bots.finance.infrastructure.state_store import PendingTransactionState
from bot_platform.bots.finance.models import InputMode, ParsedTransaction, TransactionType

from .guard_service import GuardService
from .transaction_persistence_service import TransactionPersistenceService
from .transaction_query_service import TransactionQueryService


class GroupedTransactionService:
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

    def handle_multi_transaction(
        self,
        chat_id: int,
        candidate,
        *,
        input_mode: InputMode,
        message_datetime: datetime | None,
    ) -> BotResponse:
        if candidate.kind == "ambiguous":
            self.runtime.state_store.set_pending_group(
                chat_id,
                raw_input=candidate.raw_input,
                item_inputs=candidate.item_inputs,
                item_labels=candidate.item_labels,
                shared_total_amount=candidate.shared_total_amount or 0,
                item_amounts=candidate.item_amounts,
                shared_payload=candidate.shared_payload,
                input_mode=input_mode,
            )
            return FinanceBotPolicy.format_group_confirmation_message(
                candidate.item_labels,
                candidate.shared_total_amount or 0,
                FinanceBotPolicy.source_label(input_mode),
            )

        return self.save_group_transactions(
            chat_id=chat_id,
            item_inputs=candidate.item_inputs,
            item_labels=candidate.item_labels,
            raw_input=candidate.raw_input,
            input_mode=input_mode,
            message_datetime=message_datetime,
            allocations=None,
            shared_total_amount=None,
            forced_shared_total=False,
            item_amounts=candidate.item_amounts,
            shared_payload=candidate.shared_payload,
        )

    def handle_group_pending_confirmation(
        self,
        chat_id: int,
        message_text: str,
        pending: PendingTransactionState,
    ) -> BotResponse:
        shared_total_amount = pending.shared_total_amount or 0
        normalized = " ".join(message_text.strip().lower().split())
        if any(token in normalized for token in {"force", "just do it", "paksa"}):
            return self.save_group_transactions(
                chat_id=chat_id,
                item_inputs=pending.item_inputs,
                item_labels=pending.item_labels,
                raw_input=pending.raw_input,
                input_mode=pending.input_mode,
                message_datetime=None,
                allocations=None,
                shared_total_amount=shared_total_amount,
                forced_shared_total=True,
                item_amounts=pending.item_amounts,
                shared_payload=pending.shared_payload,
            )

        allocations = parse_group_allocation_reply(
            message_text,
            expected_count=len(pending.item_inputs),
            shared_total_amount=shared_total_amount,
        )
        if allocations is None:
            self.runtime.state_store.set_pending_group(
                chat_id,
                raw_input=pending.raw_input,
                item_inputs=pending.item_inputs,
                item_labels=pending.item_labels,
                shared_total_amount=shared_total_amount,
                item_amounts=pending.item_amounts,
                shared_payload=pending.shared_payload,
                input_mode=pending.input_mode,
            )
            return FinanceBotPolicy.format_group_confirmation_message(
                pending.item_labels,
                shared_total_amount,
                FinanceBotPolicy.source_label(pending.input_mode),
            )

        return self.save_group_transactions(
            chat_id=chat_id,
            item_inputs=pending.item_inputs,
            item_labels=pending.item_labels,
            raw_input=pending.raw_input,
            input_mode=pending.input_mode,
            message_datetime=None,
            allocations=allocations,
            shared_total_amount=shared_total_amount,
            forced_shared_total=False,
            item_amounts=pending.item_amounts,
            shared_payload=pending.shared_payload,
        )

    def save_group_transactions(
        self,
        *,
        chat_id: int,
        item_inputs: list[str],
        item_labels: list[str],
        raw_input: str,
        input_mode: InputMode,
        message_datetime: datetime | None,
        allocations: list[int] | None,
        shared_total_amount: int | None,
        forced_shared_total: bool,
        item_amounts: list[int | None] | None,
        shared_payload: dict | None,
    ) -> BotResponse:
        if forced_shared_total:
            transactions = self._build_forced_shared_total_transactions(
                chat_id=chat_id,
                item_labels=item_labels,
                raw_input=raw_input,
                input_mode=input_mode,
                message_datetime=message_datetime,
                shared_total_amount=shared_total_amount,
                shared_payload=shared_payload,
            )
        else:
            transactions = self._build_direct_group_transactions(
                chat_id=chat_id,
                item_inputs=item_inputs,
                raw_input=raw_input,
                input_mode=input_mode,
                message_datetime=message_datetime,
                allocations=allocations,
                shared_total_amount=shared_total_amount,
                item_amounts=item_amounts,
                shared_payload=shared_payload,
            )
            if transactions is None:
                return BotResponse(
                    "I detected multiple items, but I could not safely save all rows yet. "
                    "Please send clearer item amounts or split them into separate messages."
                )

        self.persistence.append_transactions(chat_id, transactions)
        return FinanceBotPolicy.format_group_saved_message(transactions, forced_even_split=forced_shared_total)

    def _build_direct_group_transactions(
        self,
        *,
        chat_id: int,
        item_inputs: list[str],
        raw_input: str,
        input_mode: InputMode,
        message_datetime: datetime | None,
        allocations: list[int] | None,
        shared_total_amount: int | None,
        item_amounts: list[int | None] | None,
        shared_payload: dict | None,
    ):
        resolved_allocations = allocations or [int(amount or 0) for amount in (item_amounts or [])]
        if shared_payload is not None and resolved_allocations and len(resolved_allocations) == len(item_inputs):
            return self._build_direct_group_transactions_from_shared_payload(
                chat_id=chat_id,
                item_labels=item_inputs,
                raw_input=raw_input,
                input_mode=input_mode,
                message_datetime=message_datetime,
                allocations=resolved_allocations,
                shared_total_amount=shared_total_amount,
                shared_payload=shared_payload,
            )

        transactions = []
        group_id = f"group_{chat_id}_{abs(hash((raw_input, tuple(item_inputs))))}"
        for index, item_input in enumerate(item_inputs):
            parsed = self.runtime.ai_client.parse_transaction(item_input)
            parsed = self.queries.apply_deterministic_enrichment(parsed, raw_input, message_datetime)
            parsed = (
                parsed.model_copy(update={"amount": allocations[index], "raw_input": raw_input})
                if allocations is not None
                else parsed.model_copy(update={"raw_input": raw_input})
            )
            parsed = FinanceBotPolicy.prepare_for_save(parsed)
            if parsed.confidence < self.runtime.low_confidence_threshold or parsed.missing_fields:
                return None
            transactions.append(
                parsed.to_transaction_record(input_mode=input_mode).model_copy(
                    update={"group_id": group_id, "group_total_amount": shared_total_amount}
                )
            )
        resolved_group_total = shared_total_amount
        if resolved_group_total is None:
            resolved_group_total = sum(item.amount for item in transactions)
            transactions = [
                transaction.model_copy(update={"group_total_amount": resolved_group_total})
                for transaction in transactions
            ]
        return transactions

    def _build_direct_group_transactions_from_shared_payload(
        self,
        *,
        chat_id: int,
        item_labels: list[str],
        raw_input: str,
        input_mode: InputMode,
        message_datetime: datetime | None,
        allocations: list[int],
        shared_total_amount: int | None,
        shared_payload: dict,
    ) -> list:
        base_parsed = ParsedTransaction.model_validate(shared_payload)
        base_parsed = self.queries.apply_deterministic_enrichment(base_parsed, raw_input, message_datetime)
        base_parsed = FinanceBotPolicy.prepare_for_save(base_parsed)
        if base_parsed.type is None:
            base_parsed = base_parsed.model_copy(update={"type": TransactionType.EXPENSE})

        shared_payment_method = (
            base_parsed.payment_method
            or base_parsed.account_from
            or self.guards.extract_shared_payment_method(raw_input)
        )
        group_id = f"group_{chat_id}_{abs(hash((raw_input, tuple(item_labels), tuple(allocations))))}"
        transactions = []
        for index, label in enumerate(item_labels):
            item_name = label.strip() or "Item"
            amount = allocations[index]
            parsed = base_parsed.model_copy(
                update={
                    "raw_input": raw_input,
                    "amount": amount,
                    "payment_method": shared_payment_method,
                    "account_from": shared_payment_method,
                    "subcategory": item_name,
                    "merchant_or_source": item_name,
                    "description": item_name,
                    "needs_confirmation": False,
                    "confidence": max(base_parsed.confidence, 0.95),
                }
            )
            parsed = FinanceBotPolicy.prepare_for_save(parsed)
            if parsed.confidence < self.runtime.low_confidence_threshold or parsed.missing_fields:
                return None
            transaction = parsed.to_transaction_record(input_mode=input_mode).model_copy(
                update={
                    "group_id": group_id,
                    "group_total_amount": shared_total_amount,
                    "subcategory": item_name,
                    "merchant_or_source": item_name,
                    "description": item_name,
                }
            )
            transactions.append(transaction)
        resolved_group_total = shared_total_amount or sum(item.amount for item in transactions)
        return [
            transaction.model_copy(update={"group_total_amount": resolved_group_total})
            for transaction in transactions
        ]

    def _build_forced_shared_total_transactions(
        self,
        *,
        chat_id: int,
        item_labels: list[str],
        raw_input: str,
        input_mode: InputMode,
        message_datetime: datetime | None,
        shared_total_amount: int | None,
        shared_payload: dict | None,
    ) -> list:
        base_parsed = (
            ParsedTransaction.model_validate(shared_payload)
            if shared_payload is not None
            else self.runtime.ai_client.parse_transaction(raw_input)
        )
        base_parsed = self.queries.apply_deterministic_enrichment(base_parsed, raw_input, message_datetime)
        base_parsed = FinanceBotPolicy.prepare_for_save(base_parsed)
        if base_parsed.type is None:
            base_parsed = base_parsed.model_copy(update={"type": TransactionType.EXPENSE})

        shared_payment_method = (
            base_parsed.payment_method
            or base_parsed.account_from
            or self.guards.extract_shared_payment_method(raw_input)
        )
        shared_amount = shared_total_amount or base_parsed.amount or 0
        base_parsed = base_parsed.model_copy(
            update={
                "amount": shared_amount,
                "payment_method": shared_payment_method,
                "account_from": shared_payment_method,
                "missing_fields": [],
                "needs_confirmation": False,
            }
        )
        group_id = f"group_{chat_id}_{abs(hash((raw_input, tuple(item_labels), shared_amount)))}"
        transactions = []
        for label in item_labels:
            item_name = label.strip() or "Item"
            parsed = base_parsed.model_copy(
                update={
                    "raw_input": raw_input,
                    "subcategory": item_name,
                    "merchant_or_source": base_parsed.merchant_or_source or item_name,
                    "description": base_parsed.description or item_name,
                    "confidence": max(base_parsed.confidence, 1.0),
                }
            )
            transaction = parsed.to_transaction_record(input_mode=input_mode).model_copy(
                update={
                    "group_id": group_id,
                    "group_total_amount": shared_amount,
                    "amount": shared_amount,
                    "subcategory": item_name,
                    "merchant_or_source": item_name,
                    "description": parsed.description or item_name,
                }
            )
            transactions.append(transaction)
        return transactions
