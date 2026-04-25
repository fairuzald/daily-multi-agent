from __future__ import annotations

from datetime import datetime

from bot_platform.bots.finance.domain.extraction import FinanceMessageExtraction
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
        return self.guards.ensure_owner_with_sheet(user_id)

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

        pending_result = self._handle_pending_reply_state(chat_id, message_text, reply_context)
        if pending_result is not None:
            return pending_result

        matched_reply_context = self.guards.matched_reply_context(chat_id, reply_context)
        pending = self.runtime.state_store.get_pending(chat_id)
        extraction = self.runtime.ai_client.extract_message(
            message_text,
            reply_context_kind=matched_reply_context.kind if matched_reply_context else "",
            reply_context_text=reply_context.message_text if reply_context else "",
            pending_kind=pending.kind if pending else "",
            message_datetime_iso=message_datetime.isoformat() if message_datetime else "",
        )
        if extraction.intent == "clarify":
            clarification = extraction.clarification_message.strip() or "Aku masih belum yakin maksudmu apa. Coba jelaskan lagi dengan bahasa yang lebih spesifik."
            return BotResponse(clarification)
        parsed_command = extraction.to_command(message_text)
        if parsed_command.intent:
            return self.command_service.handle_command(chat_id, message_text, parsed_command, reply_context, message_datetime)

        if extraction.intent == "unknown":
            fallback_command = self.runtime.command_parser.parse(message_text)
            if fallback_command.intent:
                return self.command_service.handle_command(chat_id, message_text, fallback_command, reply_context, message_datetime)

        reply_result = self._handle_non_pending_reply_state(chat_id, message_text, matched_reply_context)
        if reply_result is not None:
            return reply_result

        contextual_text = self._contextual_text(message_text, reply_context)
        multi_candidate = extraction.to_multi_candidate(contextual_text)
        if multi_candidate is None:
            multi_candidate = detect_multi_transaction(contextual_text)
        if multi_candidate is not None:
            return self.grouped_service.handle_multi_transaction(
                chat_id,
                multi_candidate,
                input_mode=InputMode.TEXT,
                message_datetime=message_datetime,
            )

        parsed = next((item for item in extraction.items if item.type is not None or item.amount is not None), None)
        if parsed is None:
            parsed = self.runtime.ai_client.parse_transaction(message_text)
        parsed = self.queries.apply_deterministic_enrichment(parsed, contextual_text, message_datetime)
        return self._handle_parsed_transaction(chat_id, parsed, InputMode.TEXT)

    def handle_voice_transcript(
        self,
        user_id: int,
        chat_id: int,
        transcript: str,
        reply_context: ReplyContextInput | None = None,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error

        pending_result = self._handle_pending_reply_state(chat_id, transcript, reply_context)
        if pending_result is not None:
            return pending_result

        matched_reply_context = self.guards.matched_reply_context(chat_id, reply_context)
        pending = self.runtime.state_store.get_pending(chat_id)
        extraction = self.runtime.ai_client.extract_message(
            transcript,
            reply_context_kind=matched_reply_context.kind if matched_reply_context else "",
            reply_context_text=reply_context.message_text if reply_context else "",
            pending_kind=pending.kind if pending else "",
            message_datetime_iso=message_datetime.isoformat() if message_datetime else "",
        )
        if extraction.intent == "clarify":
            clarification = extraction.clarification_message.strip() or "Aku masih belum yakin maksud voice note itu. Coba kirim ulang dengan kalimat yang lebih jelas."
            return BotResponse(clarification)
        parsed_command = extraction.to_command(transcript)
        if parsed_command.intent:
            return self.command_service.handle_command(chat_id, transcript, parsed_command, reply_context, message_datetime)

        reply_result = self._handle_non_pending_reply_state(chat_id, transcript, matched_reply_context)
        if reply_result is not None:
            return reply_result

        contextual_text = self._contextual_text(transcript, reply_context)
        multi_candidate = extraction.to_multi_candidate(contextual_text)
        if multi_candidate is None:
            multi_candidate = detect_multi_transaction(contextual_text)
        if multi_candidate is not None:
            return self.grouped_service.handle_multi_transaction(
                chat_id,
                multi_candidate,
                input_mode=InputMode.VOICE,
                message_datetime=message_datetime,
            )

        parsed = next((item for item in extraction.items if item.type is not None or item.amount is not None), None)
        if parsed is None:
            parsed = self.runtime.ai_client.parse_transaction(transcript)
        parsed = self.queries.apply_deterministic_enrichment(parsed, contextual_text, message_datetime)
        return self._handle_parsed_transaction(chat_id, parsed, InputMode.VOICE)

    def handle_image_message(
        self,
        user_id: int,
        chat_id: int,
        extraction: FinanceMessageExtraction,
        reply_context: ReplyContextInput | None = None,
        message_datetime: datetime | None = None,
    ) -> BotResponse:
        guard_error = self._require_owner_with_sheet(user_id)
        if guard_error:
            return guard_error

        raw_input = next((item.raw_input for item in extraction.items if item.raw_input.strip()), "") or "image transaction proof"
        pending_result = self._handle_pending_reply_state(chat_id, raw_input, reply_context)
        if pending_result is not None:
            return pending_result

        multi_candidate = extraction.to_multi_candidate(raw_input)
        if multi_candidate is None:
            multi_candidate = detect_multi_transaction(self._contextual_text(raw_input, reply_context))
        if multi_candidate is not None:
            return self.grouped_service.handle_multi_transaction(
                chat_id,
                multi_candidate,
                input_mode=InputMode.IMAGE,
                message_datetime=message_datetime,
            )

        parsed = next((item for item in extraction.items if item.type is not None or item.amount is not None), None)
        if parsed is None:
            return BotResponse(extraction.clarification_message.strip() or "Aku belum bisa memahami isi gambar itu dengan cukup yakin. Coba kirim gambar yang lebih jelas atau tambahkan caption.")
        parsed = self.queries.apply_deterministic_enrichment(parsed, self._contextual_text(parsed.raw_input or raw_input, reply_context), message_datetime)
        return self._handle_parsed_transaction(chat_id, parsed, InputMode.IMAGE)

    def _handle_pending_reply_state(
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
        return None

    def _handle_non_pending_reply_state(
        self,
        chat_id: int,
        message_text: str,
        matched_reply_context,
    ) -> BotResponse | None:
        if matched_reply_context and matched_reply_context.kind == "saved":
            return self.pending_service.handle_saved_reply(chat_id, message_text, matched_reply_context)
        if matched_reply_context and matched_reply_context.kind == "summary":
            return BotResponse(
                "Replying to a summary does not edit transactions directly. "
                "Reply to a saved transaction message to correct it, or use /month MM-YYYY for another month."
            )
        return None

    @staticmethod
    def _contextual_text(message_text: str, reply_context: ReplyContextInput | None) -> str:
        reply_text = (reply_context.message_text if reply_context else "").strip()
        if not reply_text:
            return message_text
        return f"{reply_text}\n{message_text}".strip()

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
