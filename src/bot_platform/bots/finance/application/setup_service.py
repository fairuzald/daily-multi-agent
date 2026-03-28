from __future__ import annotations

from bot_platform.bots.finance.categories import DEFAULT_WALLETS
from bot_platform.bots.finance.domain.responses import BotResponse

from .guard_service import GuardService


class SetupService:
    def __init__(self, guards: GuardService) -> None:
        self.guards = guards
        self.runtime = guards.runtime

    def _require_owner(self, user_id: int) -> BotResponse | None:
        return self.guards.ensure_owner(user_id)

    def handle_start(self, user_id: int) -> BotResponse:
        auth = self.guards.ensure_owner(user_id)
        if auth:
            return auth
        if not self.runtime.state_store.get_active_sheet_id():
            self.runtime.state_store.set_awaiting_sheet_link(True)
            return BotResponse(
                "Owner verified. Send me your Google Sheets link and I will configure the sheet for you.\n\n"
                f"Share the sheet with this service account as Editor: {self.runtime.service_account_email}"
            )
        return BotResponse(
            "Finance bot is running.\n\n"
            "Active sheet is configured.\n"
            "Use /help to see commands and input examples."
        )

    def handle_help(self, user_id: int) -> BotResponse:
        auth = self._require_owner(user_id)
        if auth:
            return auth
        return BotResponse(
            "What I can do:\n"
            "- Record expense, income, and transfer from chat, voice, or screenshots\n"
            "- Split one message into multiple transactions when you mention multiple items\n"
            "- Ask follow-up questions if one total is shared across several items\n"
            "- Read Indonesian voice notes and payment or order screenshots\n"
            "- Show today, week, month, category, budget, and month-to-month summaries\n"
            "- Help fix, edit, or delete recent transactions by reply or command\n\n"
            "Try messages like:\n"
            "- beli kopi 25000 pakai bca\n"
            "- makan siang 45000 kemarin pakai gopay\n"
            "- gaji masuk 8000000 ke bri\n"
            "- transfer 500000 dari BCA ke GoPay\n"
            "- es teh 5000 dan roti bakar 12000 pakai gopay\n"
            "- nasi goreng dan es teh total 30000 pakai ovo\n"
            "- show food this week\n"
            "- show budget this month\n"
            "- compare month\n"
            "- delete last\n"
            "- edit last 25000 pakai gopay\n\n"
            "Quick commands:\n"
            "/start\n"
            "/help\n"
            "/fullhelp\n"
            "/set_sheet\n"
            "/today\n"
            "/week\n"
            "/month\n"
            "/budget_show\n"
            "/compare_month\n\n"
            "Use /fullhelp for the full command list.\n\n"
            f"For sheet setup, share your sheet with this service account as Editor:\n`{self.runtime.service_account_email}`"
        )

    def handle_full_help(self, user_id: int) -> BotResponse:
        auth = self._require_owner(user_id)
        if auth:
            return auth
        return BotResponse(
            "Full help:\n\n"
            "Natural input examples:\n"
            "- beli kopi 25000 pakai bca\n"
            "- makan siang 45000 kemarin pakai gopay\n"
            "- gaji masuk 8000000 ke bri\n"
            "- transfer 500000 dari BCA ke GoPay\n"
            "- es teh 5000 dan roti bakar 12000 pakai gopay\n"
            "- nasi goreng dan es teh total 30000 pakai ovo\n"
            "- show food this week\n"
            "- show budget this month\n"
            "- compare month\n\n"
            "Core commands:\n"
            "/start\n"
            "/help\n"
            "/fullhelp\n"
            "/full_help\n"
            "/status\n"
            "/whoami\n"
            "/set_sheet\n\n"
            "Summary commands:\n"
            "/today [YYYY-MM-DD]\n"
            "/week [YYYY-Www]\n"
            "/month [YYYY-MM]\n"
            "/read <category> <today|week|month>\n"
            "/compare_month\n\n"
            "Edit and delete commands:\n"
            "/delete_last\n"
            "/delete_reply\n"
            "/edit_last <amount> [payment_method]\n"
            "/edit_reply <amount> [payment_method]\n\n"
            "Budget commands:\n"
            "/budget_set <weekly|monthly> <global|category> <amount> [category]\n"
            "/budget_show <weekly|monthly>\n\n"
            "Setup commands:\n"
            "/add_payment_method\n"
            "/add_categories\n\n"
            "Sheet setup:\n"
            "Share your Google Sheet with this service account as Editor, then send the full sheet link.\n"
            f"`{self.runtime.service_account_email}`"
        )

    def handle_status(self, user_id: int) -> BotResponse:
        auth = self._require_owner(user_id)
        if auth:
            return auth
        owner = self.runtime.state_store.get_owner_user_id()
        active_sheet = self.runtime.state_store.get_active_sheet_id() or "-"
        awaiting = "yes" if self.runtime.state_store.is_awaiting_sheet_link() else "no"
        return BotResponse(
            f"Owner Telegram user ID: {owner}\n"
            f"Active sheet ID: {active_sheet}\n"
            f"Awaiting sheet link: {awaiting}\n"
            f"Service account email: {self.runtime.service_account_email}"
        )

    def handle_whoami(self, user_id: int) -> BotResponse:
        auth = self._require_owner(user_id)
        if auth:
            return auth
        owner = self.runtime.state_store.get_owner_user_id()
        status = "owner" if owner == user_id else "unknown"
        return BotResponse(f"Your Telegram user ID: {user_id}\nStatus: {status}")

    def handle_set_sheet(self, user_id: int) -> BotResponse:
        auth = self._require_owner(user_id)
        if auth:
            return auth
        self.runtime.state_store.set_awaiting_sheet_link(True)
        return BotResponse(
            "Send me the full Google Sheets link.\n\n"
            f"Before that, share the sheet with this service account as Editor:\n{self.runtime.service_account_email}"
        )

    def handle_add_payment_method(self, user_id: int, chat_id: int) -> BotResponse:
        auth = self._require_owner(user_id)
        if auth:
            return auth
        self.runtime.state_store.set_setup_mode(chat_id, "add_payment_method")
        return BotResponse(
            "Send one payment method name, for example: GoPay\n\n"
            f"Current defaults: {', '.join(DEFAULT_WALLETS)}"
        )

    def handle_add_categories(self, user_id: int, chat_id: int) -> BotResponse:
        auth = self._require_owner(user_id)
        if auth:
            return auth
        self.runtime.state_store.set_setup_mode(chat_id, "add_categories")
        return BotResponse("Send `type, category, subcategory`, for example: expense, Food, Dessert")
