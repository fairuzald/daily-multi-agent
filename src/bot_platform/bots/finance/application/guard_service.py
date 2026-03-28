from __future__ import annotations

import re

from bot_platform.bots.finance.categories import DEFAULT_CATEGORIES, DEFAULT_WALLETS
from bot_platform.bots.finance.domain.policies import FinanceBotPolicy
from bot_platform.bots.finance.domain.responses import BotResponse, ReplyContextInput
from bot_platform.bots.finance.infrastructure.sheets_gateway import build_category_rows
from bot_platform.bots.finance.infrastructure.state_store import (
    PendingTransactionState,
    ReplyMessageContext,
)

from .finance_bot_runtime import FinanceBotRuntime


class GuardService:
    def __init__(self, runtime: FinanceBotRuntime) -> None:
        self.runtime = runtime

    def claim_or_authorize_owner(self, user_id: int) -> bool:
        owner = self.runtime.state_store.get_owner_user_id()
        if owner is None:
            self.runtime.state_store.set_owner_user_id(user_id)
            return True
        return owner == user_id

    def is_authorized(self, user_id: int) -> bool:
        owner = self.runtime.state_store.get_owner_user_id()
        return owner is not None and owner == user_id

    @staticmethod
    def unauthorized_message() -> str:
        return "You are not authorized to use this bot."

    def ensure_owner(self, user_id: int) -> BotResponse | None:
        if self.claim_or_authorize_owner(user_id):
            return None
        return BotResponse(self.unauthorized_message())

    def ensure_authorized(self, user_id: int) -> BotResponse | None:
        if self.is_authorized(user_id):
            return None
        return BotResponse(self.unauthorized_message())

    def ensure_active_sheet(self) -> BotResponse | None:
        if self.runtime.state_store.get_active_sheet_id():
            return None
        return BotResponse("No Google Sheet is configured yet. Use /start or /set_sheet and send the sheet link first.")

    def ensure_authorized_with_sheet(self, user_id: int) -> BotResponse | None:
        auth = self.ensure_authorized(user_id)
        if auth:
            return auth
        return self.ensure_active_sheet()

    def sheets_client(self):
        sheet_id = self.runtime.state_store.get_active_sheet_id()
        if not sheet_id:
            raise RuntimeError("No active sheet configured")
        return self.runtime.sheets_client_factory(sheet_id)

    def configure_sheet_from_link(self, message_text: str) -> BotResponse:
        sheet_id = FinanceBotPolicy.extract_sheet_id(message_text)
        if not sheet_id:
            return BotResponse("That does not look like a valid Google Sheets link. Send the full spreadsheet URL.")
        client = self.runtime.sheets_client_factory(sheet_id)
        try:
            client.ensure_schema()
            client.ensure_default_categories(build_category_rows(DEFAULT_CATEGORIES))
            for payment_method in DEFAULT_WALLETS:
                client.add_payment_method(payment_method)
        except PermissionError:
            return BotResponse(
                "I could not access that sheet. Share it with the service account as Editor and send the link again.\n\n"
                f"Service account: {self.runtime.service_account_email}"
            )
        self.runtime.state_store.set_active_sheet_id(sheet_id)
        self.runtime.state_store.set_awaiting_sheet_link(False)
        return BotResponse("Sheet connected successfully. The bot is ready to save transactions.")

    def matched_reply_context(
        self,
        chat_id: int,
        reply_context: ReplyContextInput | None,
    ) -> ReplyMessageContext | None:
        if reply_context is None or not reply_context.is_bot_reply:
            return None
        return self.runtime.state_store.get_reply_context(chat_id, reply_context.message_id)

    @staticmethod
    def is_pending_confirmation_reply(
        *,
        pending: PendingTransactionState | None,
        reply_context: ReplyContextInput | None,
        matched_reply_context: ReplyMessageContext | None,
    ) -> bool:
        if pending is None or reply_context is None or not reply_context.is_bot_reply:
            return False
        if matched_reply_context is None:
            return True
        return matched_reply_context.kind == "confirmation"

    @staticmethod
    def extract_shared_payment_method(raw_text: str) -> str:
        match = re.search(
            r"\b(?:pakai|via|dengan|gunakan)\s+([a-zA-Z0-9][a-zA-Z0-9\s-]*)$",
            raw_text,
            flags=re.IGNORECASE,
        )
        if not match:
            return ""
        return match.group(1).strip()
