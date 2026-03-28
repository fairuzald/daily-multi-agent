from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from bot_platform.bots.finance.domain.command_parser import CommandParser
from bot_platform.bots.finance.domain.date_parser import DateParser
from bot_platform.bots.finance.domain.summary_service import SummaryService
from bot_platform.bots.finance.infrastructure.repositories import FinanceRepository
from bot_platform.bots.finance.infrastructure.state_store import BotStateStore


@dataclass
class FinanceBotRuntime:
    ai_client: Any
    sheets_client_factory: Callable[[str], Any]
    summary_service: SummaryService
    state_store: BotStateStore
    finance_repository: FinanceRepository
    low_confidence_threshold: float
    service_account_email: str
    date_parser: DateParser
    command_parser: CommandParser
