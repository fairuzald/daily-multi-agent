from __future__ import annotations

from datetime import datetime

from bot_platform.bots.finance.domain.multi_transaction import detect_multi_transaction
from bot_platform.bots.finance.domain.policies import FinanceBotPolicy
from bot_platform.bots.finance.domain.responses import BotResponse, ReplyContextInput
from bot_platform.bots.finance.models import InputMode, ParsedTransaction

from .command_service import CommandService
from .grouped_transaction_service import GroupedTransactionService
from .guard_service import GuardService
from .pending_transaction_service import PendingTransactionService
from .transaction_persistence_service import TransactionPersistenceService
from .transaction_query_service import TransactionQueryService


class MessageEntryService:
    def __init__(
        self,
        guards: GuardService,
        queries: TransactionQueryService,
        persistence: TransactionPersistenceService,
        pending_service: PendingTransactionService,
        grouped_service: GroupedTransactionService,
        command_service: CommandService,
    ) -> None:
        self.guards = guards
        self.queries = queries
        self.persistence = persistence
        self.pending_service = pending_service
        self.grouped_service = grouped_service
        self.command_service = command_service
        self.runtime = guards.runtime

    def _require_owner_with_sheet(self, user_id: int) -> BotResponse | None:
        auth = self.guards.ensure_owner(user_id)
        if auth:
            return auth
        return self.guards.ensure_active_sheet()

    def _require_authorized_with_sheet(self, user_id: int) -> BotResponse | None:
        return self.guards.ensure_authorized_with_sheet(user_id)

    def handle_text_message(
        self,
        user_id: int,
        chat_id: int,
        message_text: str,
        reply_context: ReplyContextInput | None = None,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        if self.runtime.state_store.is_awaiting_sheet_link():
            auth = self.guards.ensure_owner(user_id)
            if auth:
                return auth
            return self.guards.configure_sheet_from_link(message_text)
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error

        setup_mode = self.runtime.state_store.get_setup_mode(chat_id)
        if setup_mode:
            return self._handle_setup_mode(chat_id, message_text, setup_mode)

        parsed_command = self.runtime.command_parser.parse(message_text)
        if parsed_command.intent:
            return self.command_service.handle_command(chat_id, message_text, parsed_command, reply_context, message_datetime)

        pending_result = self._handle_reply_state(chat_id, message_text, reply_context)
        if pending_result is not None:
            return pending_result

        multi_candidate = detect_multi_transaction(message_text)
        if multi_candidate is not None:
            return self.grouped_service.handle_multi_transaction(
                chat_id,
                multi_candidate,
                input_mode=InputMode.TEXT,
                message_datetime=message_datetime,
            )

        parsed = self.runtime.ai_client.parse_transaction(message_text)
        parsed = self.queries.apply_deterministic_enrichment(parsed, message_text, message_datetime)
        return self._handle_parsed_transaction(chat_id, parsed, InputMode.TEXT)

    def handle_voice_transcript(
        self,
        user_id: int,
        chat_id: int,
        transcript: str,
        reply_context: ReplyContextInput | None = None,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        guard_error = self._require_authorized_with_sheet(user_id)
        if guard_error:
            return guard_error

        pending_result = self._handle_reply_state(chat_id, transcript, reply_context)
        if pending_result is not None:
            return pending_result

        multi_candidate = self.runtime.ai_client.extract_multi_transaction(transcript)
        if multi_candidate is None:
            multi_candidate = detect_multi_transaction(transcript)
        if multi_candidate is not None:
            return self.grouped_service.handle_multi_transaction(
                chat_id,
                multi_candidate,
                input_mode=InputMode.VOICE,
                message_datetime=message_datetime,
            )

        parsed = self.runtime.ai_client.parse_transaction(transcript)
        parsed = self.queries.apply_deterministic_enrichment(parsed, transcript, message_datetime)
        return self._handle_parsed_transaction(chat_id, parsed, InputMode.VOICE)

    def handle_image_message(
        self,
        user_id: int,
        chat_id: int,
        parsed: ParsedTransaction,
        reply_context: ReplyContextInput | None = None,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        guard_error = self._require_authorized_with_sheet(user_id)
        if guard_error:
            return guard_error

        pending_result = self._handle_reply_state(chat_id, parsed.raw_input, reply_context)
        if pending_result is not None:
            return pending_result

        multi_source_text = parsed.raw_input or parsed.description
        multi_candidate = self.runtime.ai_client.extract_multi_transaction(multi_source_text)
        if multi_candidate is None:
            multi_candidate = detect_multi_transaction(multi_source_text)
        if multi_candidate is not None:
            return self.grouped_service.handle_multi_transaction(
                chat_id,
                multi_candidate,
                input_mode=InputMode.IMAGE,
                message_datetime=message_datetime,
            )

        parsed = self.queries.apply_deterministic_enrichment(parsed, parsed.raw_input, message_datetime)
        return self._handle_parsed_transaction(chat_id, parsed, InputMode.IMAGE)

    def _handle_reply_state(
        self,
        chat_id: int,
        message_text: str,
        reply_context: ReplyContextInput | None,
    ) -> BotResponse | None:
        matched_reply_context = self.guards.matched_reply_context(chat_id, reply_context)
        pending = self.runtime.state_store.get_pending(chat_id)
        if self.guards.is_pending_confirmation_reply(
            pending=pending,
            reply_context=reply_context,
            matched_reply_context=matched_reply_context,
        ):
            if pending.kind == "group":
                return self.grouped_service.handle_group_pending_confirmation(chat_id, message_text, pending)
            return self.pending_service.handle_pending_confirmation(chat_id, message_text, pending)
        if pending is None and matched_reply_context and matched_reply_context.kind == "confirmation":
            return BotResponse("That confirmation context has expired. Please resend the transaction or reply to a newer bot message.")
        if matched_reply_context and matched_reply_context.kind == "saved":
            return self.pending_service.handle_saved_reply(chat_id, message_text, matched_reply_context)
        if matched_reply_context and matched_reply_context.kind == "summary":
            return BotResponse(
                "Replying to a summary does not edit transactions directly. "
                "Reply to a saved transaction message to correct it, or use /month MM-YYYY for another month."
            )
        return None

    def _handle_parsed_transaction(
        self,
        chat_id: int,
        parsed: ParsedTransaction,
        input_mode: InputMode,
    ) -> BotResponse:
        parsed = FinanceBotPolicy.prepare_for_save(parsed)
        if parsed.confidence < self.runtime.low_confidence_threshold or parsed.missing_fields:
            self.runtime.state_store.set_pending(chat_id, parsed, input_mode)
            return FinanceBotPolicy.format_confirmation_message(
                parsed,
                source_label=FinanceBotPolicy.source_label(input_mode),
            )
        transaction = parsed.to_transaction_record(input_mode=input_mode)
        self.persistence.append_transaction(chat_id, transaction)
        return FinanceBotPolicy.format_saved_message(transaction)

    def _handle_setup_mode(self, chat_id: int, message_text: str, setup_mode: str) -> BotResponse:
        if setup_mode == "add_payment_method":
            payment_method = message_text.strip()
            if not payment_method:
                return BotResponse("Payment method cannot be empty. Send one value like GoPay.")
            self.guards.sheets_client().add_payment_method(payment_method)
            self.runtime.state_store.clear_setup_mode(chat_id)
            return BotResponse(f"Payment method added: {payment_method}")

        if setup_mode == "add_categories":
            parts = [part.strip() for part in message_text.split(",")]
            if len(parts) != 3 or not all(parts):
                return BotResponse("Use `type, category, subcategory`, for example: expense, Food, Dessert")
            tx_type, category, subcategory = parts
            self.guards.sheets_client().add_category(tx_type.lower(), category, subcategory)
            self.runtime.state_store.clear_setup_mode(chat_id)
            return BotResponse(f"Category added: {tx_type.lower()} / {category} / {subcategory}")

        self.runtime.state_store.clear_setup_mode(chat_id)
        return BotResponse("That setup mode expired. Please run the command again.")
