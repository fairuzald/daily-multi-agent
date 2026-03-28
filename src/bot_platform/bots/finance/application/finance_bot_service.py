from __future__ import annotations

from bot_platform.bots.finance.domain.command_parser import CommandParser
from bot_platform.bots.finance.domain.date_parser import DateParser
from bot_platform.bots.finance.domain.summary_service import SummaryService
from bot_platform.bots.finance.infrastructure.repositories import FinanceRepository
from bot_platform.bots.finance.infrastructure.state_store import BotStateStore

from .command_service import CommandService
from .finance_bot_runtime import FinanceBotRuntime
from .grouped_transaction_service import GroupedTransactionService
from .guard_service import GuardService
from .message_entry_service import MessageEntryService
from .pending_transaction_service import PendingTransactionService
from .setup_service import SetupService
from .transaction_persistence_service import TransactionPersistenceService
from .transaction_query_service import TransactionQueryService


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
        self.runtime = FinanceBotRuntime(
            ai_client=gemini_client,
            sheets_client_factory=sheets_client_factory,
            summary_service=summary_service,
            state_store=state_store,
            finance_repository=finance_repository,
            low_confidence_threshold=low_confidence_threshold,
            service_account_email=service_account_email,
            date_parser=DateParser(default_timezone),
            command_parser=CommandParser(),
        )
        self.ai_client = self.runtime.ai_client
        self.state_store = self.runtime.state_store
        self.finance_repository = self.runtime.finance_repository
        self.summary_service = self.runtime.summary_service
        self.sheets_client_factory = self.runtime.sheets_client_factory
        self.low_confidence_threshold = self.runtime.low_confidence_threshold
        self.service_account_email = self.runtime.service_account_email
        self.date_parser = self.runtime.date_parser
        self.command_parser = self.runtime.command_parser

        self.guards = GuardService(self.runtime)
        self.queries = TransactionQueryService(self.guards)
        self.persistence = TransactionPersistenceService(self.guards)
        self.pending_service = PendingTransactionService(self.guards, self.persistence)
        self.command_service = CommandService(self.guards, self.queries, self.persistence)
        self.grouped_service = GroupedTransactionService(self.guards, self.queries, self.persistence)
        self.setup_service = SetupService(self.guards)
        self.message_service = MessageEntryService(
            self.guards,
            self.queries,
            self.persistence,
            self.pending_service,
            self.grouped_service,
            self.command_service,
        )

    def handle_start(self, user_id: int):
        return self.setup_service.handle_start(user_id)

    def handle_help(self, user_id: int):
        return self.setup_service.handle_help(user_id)

    def handle_full_help(self, user_id: int):
        return self.setup_service.handle_full_help(user_id)

    def handle_status(self, user_id: int):
        return self.setup_service.handle_status(user_id)

    def handle_whoami(self, user_id: int):
        return self.setup_service.handle_whoami(user_id)

    def handle_set_sheet(self, user_id: int):
        return self.setup_service.handle_set_sheet(user_id)

    def handle_add_payment_method(self, user_id: int, chat_id: int):
        return self.setup_service.handle_add_payment_method(user_id, chat_id)

    def handle_add_categories(self, user_id: int, chat_id: int):
        return self.setup_service.handle_add_categories(user_id, chat_id)

    def handle_text_message(self, user_id: int, chat_id: int, message_text: str, reply_context=None, message_datetime=None):
        return self.message_service.handle_text_message(user_id, chat_id, message_text, reply_context, message_datetime)

    def handle_voice_transcript(self, user_id: int, chat_id: int, transcript: str, reply_context=None, message_datetime=None):
        return self.message_service.handle_voice_transcript(user_id, chat_id, transcript, reply_context, message_datetime)

    def handle_image_message(self, user_id: int, chat_id: int, parsed, reply_context=None, message_datetime=None):
        return self.message_service.handle_image_message(user_id, chat_id, parsed, reply_context, message_datetime)

    def handle_month_command(self, user_id: int, month: str | None = None):
        return self.command_service.handle_month_command(user_id, month)

    def handle_today_command(self, user_id: int, day: str | None = None):
        return self.command_service.handle_today_command(user_id, day)

    def handle_week_command(self, user_id: int, week: str | None = None):
        return self.command_service.handle_week_command(user_id, week)

    def handle_delete_last_command(self, user_id: int, chat_id: int):
        return self.command_service.handle_delete_last_command(user_id, chat_id)

    def handle_delete_reply_command(self, user_id: int, chat_id: int, reply_context=None):
        return self.command_service.handle_delete_reply_command(user_id, chat_id, reply_context)

    def handle_edit_last_command(self, user_id: int, chat_id: int, correction_input: str, message_datetime=None):
        return self.command_service.handle_edit_last_command(user_id, chat_id, correction_input, message_datetime)

    def handle_edit_reply_command(self, user_id: int, chat_id: int, correction_input: str, reply_context=None, message_datetime=None):
        return self.command_service.handle_edit_reply_command(user_id, chat_id, correction_input, reply_context, message_datetime)

    def handle_read_strict_command(self, user_id: int, category: str, period: str, message_datetime=None):
        return self.command_service.handle_read_strict_command(user_id, category, period, message_datetime)

    def handle_budget_set_command(self, user_id: int, period: str, scope: str, amount: int, category: str = ""):
        return self.command_service.handle_budget_set_command(user_id, period, scope, amount, category)

    def handle_budget_show_command(self, user_id: int, period: str, message_datetime=None):
        return self.command_service.handle_budget_show_command(user_id, period, message_datetime)

    def handle_compare_month_command(self, user_id: int, message_datetime=None):
        return self.command_service.handle_compare_month_command(user_id, message_datetime)
