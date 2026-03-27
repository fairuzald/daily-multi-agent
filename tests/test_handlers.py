import pytest

from datetime import date

from bot_platform.bots.finance.application.finance_bot_service import FinanceBotService
from bot_platform.bots.finance.domain.summary_service import SummaryService
from bot_platform.bots.finance.models import InputMode, ParsedTransaction, TransactionRecord


class FakeGeminiClient:
    def __init__(self, parsed: ParsedTransaction) -> None:
        self.parsed = parsed

    def parse_transaction(self, raw_input: str) -> ParsedTransaction:
        return self.parsed.model_copy(update={"raw_input": raw_input})

    def correct_transaction(self, original: TransactionRecord, correction_input: str) -> ParsedTransaction:
        amount_digits = "".join(ch for ch in correction_input if ch.isdigit())
        payment_method = original.payment_method or original.account_from
        lowered = correction_input.lower()
        if "gopay" in lowered:
            payment_method = "GoPay"
        elif "bca" in lowered:
            payment_method = "BCA"
        amount = int(amount_digits) if amount_digits else original.amount
        return ParsedTransaction(
            type=original.type,
            amount=amount,
            category=original.category,
            subcategory=original.subcategory,
            account_from=payment_method,
            account_to=original.account_to,
            merchant_or_source=original.merchant_or_source,
            description=original.description or "updated transaction",
            payment_method=payment_method,
            raw_input=correction_input,
            confidence=0.95,
        )


class FakeSheetsClient:
    def __init__(self) -> None:
        self.saved_transactions: list[TransactionRecord] = []
        self.summary = None
        self.transactions_payload: list[dict[str, str]] = []
        self.schema_ensured = False
        self.categories_replaced = False
        self.default_categories_ensured = False
        self.payment_methods_added: list[str] = []
        self.categories_added: list[tuple[str, str, str]] = []

    def append_transaction(self, transaction: TransactionRecord) -> None:
        self.saved_transactions.append(transaction)

    def update_transaction(self, transaction: TransactionRecord) -> None:
        for index, current in enumerate(self.saved_transactions):
            if current.transaction_id == transaction.transaction_id:
                self.saved_transactions[index] = transaction
                return
        raise ValueError("transaction not found")

    def read_transactions(self) -> list[dict[str, str]]:
        return self.transactions_payload

    def replace_summary(self, summary) -> None:
        self.summary = summary

    def ensure_schema(self) -> None:
        self.schema_ensured = True

    def replace_categories(self, rows) -> None:
        self.categories_replaced = True

    def ensure_default_categories(self, rows) -> None:
        self.default_categories_ensured = True

    def add_payment_method(self, payment_method: str) -> None:
        self.payment_methods_added.append(payment_method)

    def add_category(self, tx_type: str, category: str, subcategory: str) -> None:
        self.categories_added.append((tx_type, category, subcategory))


class FakeStateStore:
    def __init__(self) -> None:
        self.owner_user_id: int | None = None
        self.active_sheet_id = ""
        self.awaiting_sheet_link = False
        self.pending = {}
        self.last_transaction_ids = {}
        self.reply_contexts = {}
        self.transaction_snapshots = {}
        self.setup_modes = {}

    def get_owner_user_id(self) -> int | None:
        return self.owner_user_id

    def set_owner_user_id(self, user_id: int) -> None:
        self.owner_user_id = user_id

    def get_active_sheet_id(self) -> str:
        return self.active_sheet_id

    def set_active_sheet_id(self, sheet_id: str) -> None:
        self.active_sheet_id = sheet_id

    def is_awaiting_sheet_link(self) -> bool:
        return self.awaiting_sheet_link

    def set_awaiting_sheet_link(self, awaiting: bool) -> None:
        self.awaiting_sheet_link = awaiting

    def set_pending(self, chat_id: int, parsed: ParsedTransaction, input_mode: InputMode = InputMode.TEXT) -> None:
        self.pending[chat_id] = type("Pending", (), {"chat_id": chat_id, "parsed": parsed, "input_mode": input_mode})()

    def get_pending(self, chat_id: int):
        return self.pending.get(chat_id)

    def clear_pending(self, chat_id: int) -> None:
        self.pending.pop(chat_id, None)

    def set_last_transaction_id(self, chat_id: int, transaction_id: str) -> None:
        self.last_transaction_ids[chat_id] = transaction_id

    def get_last_transaction_id(self, chat_id: int) -> str | None:
        return self.last_transaction_ids.get(chat_id)

    def set_reply_context(self, chat_id: int, message_id: int, context) -> None:
        self.reply_contexts[(chat_id, message_id)] = context

    def get_reply_context(self, chat_id: int, message_id: int | None):
        return self.reply_contexts.get((chat_id, message_id))

    def set_transaction_snapshot(self, transaction: TransactionRecord) -> None:
        self.transaction_snapshots[transaction.transaction_id] = transaction

    def get_transaction_snapshot(self, transaction_id: str):
        return self.transaction_snapshots.get(transaction_id)

    def set_setup_mode(self, chat_id: int, mode: str) -> None:
        self.setup_modes[chat_id] = mode

    def get_setup_mode(self, chat_id: int) -> str:
        return self.setup_modes.get(chat_id, "")

    def clear_setup_mode(self, chat_id: int) -> None:
        self.setup_modes.pop(chat_id, None)


class FakeFinanceRepository:
    def __init__(self) -> None:
        self.budget_rules = []
        self.learned_mappings = []

    def list_budget_rules(self):
        return list(self.budget_rules)

    def save_budget_rule(self, rule) -> None:
        self.budget_rules = [
            item
            for item in self.budget_rules
            if not (item.scope == rule.scope and item.period == rule.period and item.category == rule.category)
        ]
        self.budget_rules.append(rule)

    def list_learned_mappings(self):
        return list(self.learned_mappings)

    def save_learned_mapping(self, mapping) -> None:
        self.learned_mappings = [item for item in self.learned_mappings if item.pattern.lower() != mapping.pattern.lower()]
        self.learned_mappings.append(mapping)


def build_handlers(parsed: ParsedTransaction, sheets: FakeSheetsClient, state_store: FakeStateStore | None = None) -> FinanceBotService:
    return FinanceBotService(
        gemini_client=FakeGeminiClient(parsed),
        sheets_client_factory=lambda _sheet_id: sheets,
        summary_service=SummaryService(),
        state_store=state_store or FakeStateStore(),
        finance_repository=FakeFinanceRepository(),
        service_account_email="service@example.com",
    )


def test_start_claims_owner_and_requests_sheet_link() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    handlers = build_handlers(parsed, FakeSheetsClient())

    reply = handlers.handle_start(user_id=12345)

    assert "Owner verified" in reply
    assert "service@example.com" in reply


def test_text_message_with_sheet_link_configures_sheet() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)

    reply = handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    assert reply == "Sheet connected successfully. The bot is ready to save transactions."
    assert sheets.schema_ensured is True
    assert sheets.default_categories_ensured is True
    assert "GoPay" in sheets.payment_methods_added


def test_unauthorized_user_is_rejected() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    handlers = build_handlers(parsed, FakeSheetsClient())
    handlers.handle_start(user_id=12345)

    reply = handlers.handle_help(user_id=99999)

    assert reply == "You are not authorized to use this bot."


def test_handle_text_message_saves_high_confidence_transaction() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=25000,
        category="Food",
        subcategory="Coffee",
        description="kopi",
        payment_method="BCA",
        account_from="BCA",
        raw_input="beli kopi 25 ribu",
        confidence=0.93,
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="beli kopi 25 ribu")

    assert reply.startswith("Saved:")
    assert len(sheets.saved_transactions) == 1


def test_high_confidence_transaction_with_needs_confirmation_but_all_required_fields_still_saves() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=25000,
        category="Food",
        subcategory="Coffee",
        description="iced coffee",
        payment_method="BCA",
        raw_input="beli kopi 25 ribu",
        confidence=0.93,
        needs_confirmation=True,
        missing_fields=[],
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="beli kopi 25 ribu")

    assert reply.startswith("Saved:")
    assert len(sheets.saved_transactions) == 1


def test_missing_payment_method_still_requires_confirmation_even_when_confident() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=25000,
        category="Food",
        subcategory="Coffee",
        description="iced coffee",
        payment_method="",
        raw_input="beli kopi 25 ribu",
        confidence=0.93,
        missing_fields=[],
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="beli kopi 25 ribu")

    assert "Still missing or uncertain: payment_method" in reply
    assert len(sheets.saved_transactions) == 0


def test_follow_up_yes_saves_pending_transaction() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=16000,
        category="Food",
        subcategory="Coffee",
        description="kopi",
        payment_method="Cash",
        raw_input="beli kopi 16000",
        confidence=0.75,
        needs_confirmation=True,
        missing_fields=[],
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    first_reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="beli kopi 16000")
    second_reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="yes")

    assert "confidence is still low" in first_reply
    assert second_reply.startswith("Saved:")
    assert len(sheets.saved_transactions) == 1


def test_follow_up_yes_does_not_save_when_required_fields_are_missing() -> None:
    parsed = ParsedTransaction(
        type=None,
        amount=16000,
        category="Food",
        subcategory="Coffee",
        description="kopi",
        payment_method="Cash",
        raw_input="beli kopi 16000",
        confidence=0.4,
        needs_confirmation=True,
        missing_fields=["type"],
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )
    handlers.state_store.set_pending(12345, parsed)

    reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="yes")

    assert "core fields are missing: type" in reply
    assert len(sheets.saved_transactions) == 0


def test_follow_up_can_fill_missing_type_from_history() -> None:
    parsed = ParsedTransaction(
        type=None,
        amount=16000,
        category="Food",
        subcategory="Coffee",
        description="kopi",
        payment_method="Cash",
        raw_input="beli kopi 16000",
        confidence=0.4,
        needs_confirmation=True,
        missing_fields=["type"],
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )
    handlers.state_store.set_pending(12345, parsed)

    reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="expense")

    assert reply.startswith("Saved:")
    assert len(sheets.saved_transactions) == 1


def test_follow_up_type_answer_keeps_enum_shape_for_confirmation_message() -> None:
    parsed = ParsedTransaction(
        type=None,
        amount=16000,
        category="Food",
        subcategory="Coffee",
        description="kopi",
        payment_method="Cash",
        raw_input="beli kopi 16000",
        confidence=0.4,
        needs_confirmation=True,
        missing_fields=["type", "amount"],
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )
    handlers.state_store.set_pending(12345, parsed)

    reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="expense")

    assert "Type: expense" in reply
    assert "Still missing or uncertain: amount" in reply


def test_handle_voice_transcript_saves_voice_transaction() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=22000,
        category="Food",
        subcategory="Meals",
        description="makan",
        payment_method="GoPay",
        account_from="GoPay",
        raw_input="beli makan 22000 pakai gopay",
        confidence=0.91,
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    reply = handlers.handle_voice_transcript(user_id=12345, chat_id=12345, transcript="beli makan 22000 pakai gopay")

    assert reply.startswith("Saved:")
    assert len(sheets.saved_transactions) == 1
    assert sheets.saved_transactions[0].input_mode.value == "voice"


def test_handle_image_message_saves_image_transaction() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=550000,
        category="Bills",
        subcategory="Internet",
        description="wifi bill",
        payment_method="BCA",
        raw_input="tokopedia tagihan wifi",
        confidence=0.91,
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    reply = handlers.handle_image_message(user_id=12345, chat_id=12345, parsed=parsed)

    assert reply.startswith("Saved:")
    assert len(sheets.saved_transactions) == 1
    assert sheets.saved_transactions[0].input_mode.value == "image"


def test_pending_voice_confirmation_preserves_voice_input_mode() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=22000,
        category="Food",
        subcategory="Meals",
        description="makan",
        payment_method="GoPay",
        raw_input="beli makan 22000 pakai gopay",
        confidence=0.60,
        needs_confirmation=True,
        missing_fields=[],
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    first_reply = handlers.handle_voice_transcript(user_id=12345, chat_id=12345, transcript=parsed.raw_input)
    second_reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="yes")

    assert "voice note" in first_reply
    assert second_reply.startswith("Saved:")
    assert sheets.saved_transactions[0].input_mode.value == "voice"


def test_yes_force_saves_pending_when_only_optional_fields_are_missing() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=38000,
        category="Other",
        subcategory="",
        description="Transfer to Zaiq",
        payment_method="e-wallet",
        merchant_or_source="Zaiq",
        raw_input="image transaction proof",
        confidence=0.72,
        needs_confirmation=True,
        missing_fields=["subcategory"],
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    first_reply = handlers.handle_image_message(user_id=12345, chat_id=12345, parsed=parsed)
    second_reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="yes")

    assert "need confirmation" in first_reply.lower()
    assert second_reply.startswith("Saved:")
    assert len(sheets.saved_transactions) == 1
    assert sheets.saved_transactions[0].subcategory == "Zaiq"
    assert sheets.saved_transactions[0].category == "Transfer"


def test_yes_force_save_still_refuses_when_core_fields_are_missing() -> None:
    parsed = ParsedTransaction(
        type=None,
        amount=23000,
        category="Food & Drinks",
        subcategory="Coffee",
        description="Pembelian kopi di Tomoro Coffee",
        payment_method="",
        merchant_or_source="Tomoro Coffee",
        raw_input="voice transcript",
        confidence=0.65,
        needs_confirmation=True,
        missing_fields=["type"],
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    handlers.handle_voice_transcript(user_id=12345, chat_id=12345, transcript=parsed.raw_input)
    second_reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="yes")

    assert "core fields are missing: type" in second_reply
    assert len(sheets.saved_transactions) == 0


def test_prepare_for_save_infers_food_coffee_category_and_subcategory() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=23000,
        category="",
        subcategory="",
        description="",
        payment_method="GoPay",
        merchant_or_source="Tomoro Coffee",
        raw_input="beli kopi tomoro pakai gopay",
        confidence=0.95,
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="beli kopi tomoro pakai gopay")

    assert reply.startswith("Saved:")
    assert sheets.saved_transactions[0].category == "Coffee"
    assert sheets.saved_transactions[0].subcategory == "Tomoro Coffee"
    assert sheets.saved_transactions[0].description == "Tomoro Coffee"


def test_handle_image_message_with_zero_amount_becomes_confirmation_not_crash() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=0,
        category="Food",
        subcategory="Coffee",
        description="receipt",
        payment_method="BRI",
        raw_input="image transaction proof",
        confidence=0.95,
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    reply = handlers.handle_image_message(user_id=12345, chat_id=12345, parsed=parsed)

    assert "Still missing or uncertain: amount" in reply
    assert len(sheets.saved_transactions) == 0


def test_handle_image_message_clears_non_transfer_account_to_before_save() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=152000,
        category="Food",
        subcategory="Coffee",
        description="receipt",
        payment_method="BRI",
        account_from="BRI",
        account_to="Jabarano",
        raw_input="image transaction proof",
        confidence=0.95,
    )
    sheets = FakeSheetsClient()
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    reply = handlers.handle_image_message(user_id=12345, chat_id=12345, parsed=parsed)

    assert reply.startswith("Saved:")
    assert sheets.saved_transactions[0].account_to == ""


def test_handle_month_command_builds_and_stores_summary() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    sheets.transactions_payload = [
        {
            "Transaction ID": "txn_001",
            "Transaction Date": "2026-03-02",
            "Type": "income",
            "Amount": "5000000",
            "Category": "Salary",
            "Subcategory": "",
            "Account / Wallet": "BCA",
            "Destination Account / Wallet": "",
            "Merchant / Source": "Salary",
            "Description": "",
            "Payment Method": "",
            "Input Mode": "text",
            "Raw Input": "gaji",
            "AI Confidence": "0.99",
            "Status": "confirmed",
        },
        {
            "Transaction ID": "txn_002",
            "Transaction Date": "2026-03-03",
            "Type": "expense",
            "Amount": "1000000",
            "Category": "Food",
            "Subcategory": "",
            "Account / Wallet": "BCA",
            "Destination Account / Wallet": "",
            "Merchant / Source": "",
            "Description": "",
            "Payment Method": "",
            "Input Mode": "text",
            "Raw Input": "makan",
            "AI Confidence": "0.90",
            "Status": "confirmed",
        },
    ]
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    message = handlers.handle_month_command(user_id=12345, month="2026-03")

    assert "Summary for 2026-03" in message
    assert sheets.summary is not None
    assert any(item.insight_type for item in sheets.summary.insights)


def test_handle_month_command_accepts_mm_yyyy_format() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    sheets.transactions_payload = [
        {
            "Transaction ID": "txn_001",
            "Transaction Date": "2025-03-02",
            "Type": "income",
            "Amount": "5000000",
            "Category": "Salary",
            "Subcategory": "",
            "Account / Wallet": "BCA",
            "Destination Account / Wallet": "",
            "Merchant / Source": "Salary",
            "Description": "",
            "Payment Method": "",
            "Input Mode": "text",
            "Raw Input": "gaji",
            "AI Confidence": "0.99",
            "Status": "confirmed",
        },
    ]
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    message = handlers.handle_month_command(user_id=12345, month="03-2025")

    assert "Summary for 2025-03" in message


def test_handle_today_command_defaults_to_today(monkeypatch) -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    today = date(2026, 3, 23)
    sheets.transactions_payload = [
        {
            "Transaction ID": "txn_001",
            "Transaction Date": "2026-03-23",
            "Type": "expense",
            "Amount": "23000",
            "Category": "Coffee",
            "Subcategory": "Tomoro Coffee",
            "Description": "Tomoro Coffee",
            "Payment Method": "GoPay",
            "Destination Account / Wallet": "",
            "Merchant / Source": "Tomoro Coffee",
            "Input Mode": "voice",
            "Raw Input": "voice",
            "AI Confidence": "0.90",
            "Status": "confirmed",
        }
    ]
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0")
    monkeypatch.setattr(
        "bot_platform.bots.finance.domain.policies.date",
        type("FakeDate", (), {"today": staticmethod(lambda: today), "fromisoformat": date.fromisoformat}),
    )

    message = handlers.handle_today_command(user_id=12345)

    assert "Summary for 2026-03-23" in message
    assert "Expenses: Rp23.000" in message


def test_handle_week_command_accepts_iso_date_and_groups_same_week() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    sheets.transactions_payload = [
        {
            "Transaction ID": "txn_001",
            "Transaction Date": "2026-03-23",
            "Type": "expense",
            "Amount": "23000",
            "Category": "Coffee",
            "Subcategory": "Tomoro Coffee",
            "Description": "Tomoro Coffee",
            "Payment Method": "GoPay",
            "Destination Account / Wallet": "",
            "Merchant / Source": "Tomoro Coffee",
            "Input Mode": "voice",
            "Raw Input": "voice",
            "AI Confidence": "0.90",
            "Status": "confirmed",
        },
        {
            "Transaction ID": "txn_002",
            "Transaction Date": "2026-03-25",
            "Type": "expense",
            "Amount": "50000",
            "Category": "Lunch",
            "Subcategory": "Warteg",
            "Description": "Lunch",
            "Payment Method": "BCA",
            "Destination Account / Wallet": "",
            "Merchant / Source": "Warteg",
            "Input Mode": "text",
            "Raw Input": "lunch",
            "AI Confidence": "0.95",
            "Status": "confirmed",
        },
    ]
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0")

    message = handlers.handle_week_command(user_id=12345, week="2026-03-23")

    assert "Summary for 2026-W13" in message
    assert "Expenses: Rp73.000" in message


def test_handle_month_command_tolerates_legacy_ai_confidence_status_cell() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    sheets.transactions_payload = [
        {
            "Transaction ID": "txn_001",
            "Transaction Date": "2026-03-07",
            "Type": "expense",
            "Amount": "38000",
            "Category": "Transfer",
            "Subcategory": "Zaiq",
            "Description": "Transfer to Zaiq",
            "Payment Method": "GoPay",
            "Destination Account / Wallet": "",
            "Merchant / Source": "Zaiq",
            "Input Mode": "image",
            "Raw Input": "proof",
            "AI Confidence": "confirmed",
            "Status": "",
        }
    ]
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    message = handlers.handle_month_command(user_id=12345, month="2026-03")

    assert "Summary for 2026-03" in message
    assert "Expenses: Rp38.000" in message


def test_handle_month_command_tolerates_legacy_shifted_input_mode_cell() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    sheets.transactions_payload = [
        {
            "Transaction ID": "txn_001",
            "Transaction Date": "2026-03-23",
            "Type": "expense",
            "Amount": "23000",
            "Category": "Coffee",
            "Subcategory": "Tomoro Coffee",
            "Description": "Tomoro Coffee",
            "Payment Method": "GoPay",
            "Destination Account / Wallet": "",
            "Merchant / Source": "Tomoro Coffee",
            "Input Mode": "Gua baru beli kopi di Tomoro Coffee seharga Rp23.000.",
            "Raw Input": "",
            "AI Confidence": "confirmed",
            "Status": "",
        }
    ]
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    message = handlers.handle_month_command(user_id=12345, month="2026-03")

    assert "Summary for 2026-03" in message
    assert "Expenses: Rp23.000" in message


def test_handle_month_command_ignores_non_transfer_destination_for_summary_loading() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    sheets.transactions_payload = [
        {
            "Transaction ID": "txn_001",
            "Transaction Date": "2026-03-23",
            "Type": "expense",
            "Amount": "155000",
            "Category": "Transfer",
            "Subcategory": "NAMU BERSIH SEJAHTER",
            "Description": "Transfer to NAMU BERSIH SEJAHTER",
            "Payment Method": "BCA",
            "Destination Account / Wallet": "Mandiri",
            "Merchant / Source": "NAMU BERSIH SEJAHTER",
            "Input Mode": "image",
            "Raw Input": "proof",
            "AI Confidence": "0.88",
            "Status": "confirmed",
        }
    ]
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0")

    message = handlers.handle_month_command(user_id=12345, month="2026-03")

    assert "Summary for 2026-03" in message
    assert "Expenses: Rp155.000" in message


def test_handle_month_command_skips_badly_shifted_non_numeric_rows_instead_of_crashing() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    sheets.transactions_payload = [
        {
            "Transaction ID": "txn_bad",
            "Transaction Date": "2026-03-23",
            "Type": "expense",
            "Amount": "expense",
            "Category": "Coffee",
            "Subcategory": "Tomoro Coffee",
            "Description": "Tomoro Coffee",
            "Payment Method": "GoPay",
            "Destination Account / Wallet": "",
            "Merchant / Source": "Tomoro Coffee",
            "Input Mode": "text",
            "Raw Input": "bad row",
            "AI Confidence": "0.95",
            "Status": "confirmed",
        }
    ]
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0")

    message = handlers.handle_month_command(user_id=12345, month="2026-03")

    assert "Summary for 2026-03" in message


def test_handle_month_command_rejects_invalid_month_format() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    handlers = build_handlers(parsed, FakeSheetsClient())
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    with pytest.raises(ValueError):
        handlers.handle_month_command(user_id=12345, month="2025/03")


def test_reply_to_saved_message_updates_existing_transaction() -> None:
    parsed = ParsedTransaction(
        type="expense",
        amount=25000,
        category="Food",
        subcategory="Coffee",
        description="kopi",
        payment_method="BCA",
        account_from="BCA",
        raw_input="beli kopi 25 ribu",
        confidence=0.93,
    )
    sheets = FakeSheetsClient()
    state_store = FakeStateStore()
    handlers = build_handlers(parsed, sheets, state_store=state_store)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    first_reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="beli kopi 25 ribu")
    state_store.set_reply_context(12345, 2001, first_reply.reply_context)

    reply = handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="ubah jadi 30000 pakai gopay",
        reply_context=type("ReplyContext", (), {"message_id": 2001, "is_bot_reply": True})(),
    )

    assert reply.startswith("Updated:")
    assert len(sheets.saved_transactions) == 1
    assert sheets.saved_transactions[0].amount == 30000
    assert sheets.saved_transactions[0].account_from == "GoPay"
    assert sheets.saved_transactions[0].status.value == "edited"


def test_reply_to_summary_gets_guidance_message() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    state_store = FakeStateStore()
    handlers = build_handlers(parsed, sheets, state_store=state_store)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )
    state_store.set_reply_context(12345, 3001, type("Ctx", (), {"kind": "summary", "transaction_id": "", "month": "2026-03"})())

    reply = handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="kenapa food tinggi",
        reply_context=type("ReplyContext", (), {"message_id": 3001, "is_bot_reply": True})(),
    )

    assert "Replying to a summary does not edit transactions directly" in reply


def test_add_payment_method_command_and_follow_up() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    state_store = FakeStateStore()
    handlers = build_handlers(parsed, sheets, state_store=state_store)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    prompt = handlers.handle_add_payment_method(user_id=12345, chat_id=12345)
    reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="Jenius")

    assert "Send one payment method name" in prompt
    assert reply == "Payment method added: Jenius"
    assert "Jenius" in sheets.payment_methods_added


def test_add_categories_command_and_follow_up() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    state_store = FakeStateStore()
    handlers = build_handlers(parsed, sheets, state_store=state_store)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    prompt = handlers.handle_add_categories(user_id=12345, chat_id=12345)
    reply = handlers.handle_text_message(user_id=12345, chat_id=12345, message_text="expense, Food, Dessert")

    assert "Send `type, category, subcategory`" in prompt
    assert reply == "Category added: expense / Food / Dessert"
    assert ("expense", "Food", "Dessert") in sheets.categories_added


def test_handle_month_command_carries_forward_merged_transaction_dates() -> None:
    parsed = ParsedTransaction(type="expense", amount=1, category="Other", raw_input="noop", confidence=1.0)
    sheets = FakeSheetsClient()
    sheets.transactions_payload = [
        {
            "Transaction ID": "txn_001",
            "Transaction Date": "2026-03-02",
            "Type": "income",
            "Amount": "5000000",
            "Category": "Salary",
            "Subcategory": "",
            "Account / Wallet": "BCA",
            "Destination Account / Wallet": "",
            "Merchant / Source": "Salary",
            "Description": "",
            "Payment Method": "",
            "Input Mode": "text",
            "Raw Input": "gaji",
            "AI Confidence": "0.99",
            "Status": "confirmed",
        },
        {
            "Transaction ID": "txn_002",
            "Transaction Date": "",
            "Type": "expense",
            "Amount": "1000000",
            "Category": "Food",
            "Subcategory": "",
            "Account / Wallet": "BCA",
            "Destination Account / Wallet": "",
            "Merchant / Source": "",
            "Description": "",
            "Payment Method": "",
            "Input Mode": "text",
            "Raw Input": "makan",
            "AI Confidence": "0.90",
            "Status": "confirmed",
        },
    ]
    handlers = build_handlers(parsed, sheets)
    handlers.handle_start(user_id=12345)
    handlers.handle_text_message(
        user_id=12345,
        chat_id=12345,
        message_text="https://docs.google.com/spreadsheets/d/testSheet123/edit#gid=0",
    )

    message = handlers.handle_month_command(user_id=12345, month="2026-03")

    assert "Income: Rp5.000.000" in message
    assert "Expenses: Rp1.000.000" in message
