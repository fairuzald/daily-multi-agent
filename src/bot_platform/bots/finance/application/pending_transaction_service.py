from __future__ import annotations

from bot_platform.bots.finance.domain.policies import FinanceBotPolicy
from bot_platform.bots.finance.domain.responses import BotResponse
from bot_platform.bots.finance.infrastructure.state_store import PendingTransactionState, ReplyMessageContext
from bot_platform.bots.finance.models import InputMode, ParsedTransaction, TransactionStatus

from .guard_service import GuardService
from .transaction_persistence_service import TransactionPersistenceService


class PendingTransactionService:
    def __init__(
        self,
        guards: GuardService,
        persistence: TransactionPersistenceService,
    ) -> None:
        self.guards = guards
        self.persistence = persistence
        self.runtime = guards.runtime

    def handle_pending_confirmation(self, chat_id: int, message_text: str, pending: PendingTransactionState) -> BotResponse:
        if pending.parsed is None:
            self.runtime.state_store.clear_pending(chat_id)
            return BotResponse("That pending transaction expired. Please send it again.")
        parsed = pending.parsed
        normalized = message_text.strip().lower()
        if normalized in {"yes", "y", "ok", "oke", "correct", "confirm", "save", "ya", "iya", "betul"}:
            return self.force_save_pending(chat_id, parsed, pending.input_mode)

        updated = self._apply_follow_up_answer(parsed, message_text)
        if not updated.missing_fields:
            return self.save_pending(chat_id, updated, pending.input_mode)
        self.runtime.state_store.set_pending(chat_id, updated, pending.input_mode)
        return FinanceBotPolicy.format_confirmation_message(updated)

    def save_pending(self, chat_id: int, parsed: ParsedTransaction, input_mode: InputMode) -> BotResponse:
        finalized = FinanceBotPolicy.prepare_for_save(parsed)
        if finalized.missing_fields:
            self.runtime.state_store.set_pending(chat_id, finalized, input_mode)
            return FinanceBotPolicy.format_confirmation_message(
                finalized,
                source_label=FinanceBotPolicy.source_label(input_mode),
            )
        transaction = finalized.to_transaction_record(input_mode=input_mode)
        self.persistence.append_transaction(chat_id, transaction)
        self.runtime.state_store.clear_pending(chat_id)
        return FinanceBotPolicy.format_saved_message(transaction)

    def force_save_pending(self, chat_id: int, parsed: ParsedTransaction, input_mode: InputMode) -> BotResponse:
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
            self.runtime.state_store.set_pending(chat_id, restored, input_mode)
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

        transaction = transaction.model_copy(update={"status": TransactionStatus.REVIEWED})
        self.persistence.append_transaction(chat_id, transaction)
        self.runtime.state_store.clear_pending(chat_id)
        return FinanceBotPolicy.format_saved_message(transaction)

    def handle_saved_reply(
        self,
        chat_id: int,
        message_text: str,
        reply_context: ReplyMessageContext,
    ) -> BotResponse:
        original = self.runtime.state_store.get_transaction_snapshot(reply_context.transaction_id)
        if original is None:
            return BotResponse(
                "I could not find the original transaction behind that reply anymore. "
                "Please resend the corrected transaction as a new message."
            )
        corrected = self.runtime.ai_client.correct_transaction(original=original, correction_input=message_text)
        corrected = FinanceBotPolicy.prepare_for_save(corrected)
        if corrected.confidence < self.runtime.low_confidence_threshold or corrected.missing_fields:
            self.runtime.state_store.set_pending(chat_id, corrected, original.input_mode)
            return FinanceBotPolicy.format_confirmation_message(corrected, source_label="reply update")

        updated_record = corrected.to_transaction_record(input_mode=original.input_mode).model_copy(
            update={"transaction_id": original.transaction_id, "status": TransactionStatus.EDITED}
        )
        self.persistence.update_transaction(updated_record)
        return BotResponse(
            f"Updated: {updated_record.type.value.title()} Rp{updated_record.amount:,}".replace(",", "."),
            reply_context=ReplyMessageContext(kind="saved", transaction_id=updated_record.transaction_id),
        )

    @staticmethod
    def _apply_follow_up_answer(parsed: ParsedTransaction, message_text: str) -> ParsedTransaction:
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
