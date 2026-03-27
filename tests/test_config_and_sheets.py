from bot_platform.shared.config.settings import Settings
from bot_platform.bots.finance.infrastructure.sheets_gateway import GoogleSheetsClient, SHEET_SCHEMAS


def test_settings_accept_inline_service_account_json() -> None:
    settings = Settings(
        telegram_bot_token="token",
        gemini_api_key="gemini",
        database_url="postgresql://example",
        google_sheet_id="sheet-id",
        google_service_account_json='{"type":"service_account"}',
    )

    assert settings.validate_required() == []


def test_sheets_client_parses_inline_service_account_json() -> None:
    client = GoogleSheetsClient(spreadsheet_id="sheet-id", service_account_json='{"type":"service_account","project_id":"demo"}')

    assert client._credentials_config() == {"type": "service_account", "project_id": "demo"}


def test_sheets_client_rejects_invalid_inline_service_account_json() -> None:
    client = GoogleSheetsClient(spreadsheet_id="sheet-id", service_account_json="{invalid json")

    try:
        client._credentials_config()
    except ValueError as exc:
        assert "not valid JSON" in str(exc)
    else:
        raise AssertionError("Expected invalid JSON to raise ValueError")


def test_ensure_schema_clears_and_rewrites_headers_without_deleting_all_rows() -> None:
    calls: list[str] = []

    class FakeWorksheet:
        def __init__(self, title: str, header: list[str]) -> None:
            self.title = title
            self._header = header

        def row_values(self, index: int) -> list[str]:
            assert index == 1
            return self._header

        def clear(self) -> None:
            calls.append(f"clear:{self.title}")
            self._header = []

        def append_row(self, values, value_input_option=None) -> None:
            calls.append(f"append:{self.title}")
            self._header = list(values)

    class FakeSpreadsheet:
        def __init__(self) -> None:
            self._worksheets = [
                FakeWorksheet("Transactions", ["wrong", "header"]),
                FakeWorksheet("Categories", SHEET_SCHEMAS["Categories"]),
                FakeWorksheet("Summary", SHEET_SCHEMAS["Summary"]),
            ]

        def worksheets(self):
            return self._worksheets

        def worksheet(self, name: str):
            return next(sheet for sheet in self._worksheets if sheet.title == name)

        def add_worksheet(self, title: str, rows: int, cols: int):
            sheet = FakeWorksheet(title, [])
            self._worksheets.append(sheet)
            return sheet

        def del_worksheet(self, worksheet) -> None:
            self._worksheets.remove(worksheet)

    client = GoogleSheetsClient(spreadsheet_id="sheet-id", service_account_json='{"type":"service_account"}')
    spreadsheet = FakeSpreadsheet()
    client._spreadsheet = lambda: spreadsheet  # type: ignore[method-assign]

    client.ensure_schema()

    assert calls == ["clear:Transactions", "append:Transactions"]


def test_update_transaction_rewrites_existing_row() -> None:
    updates: list[tuple[str, list[list[str]]]] = []

    class FakeWorksheet:
        def get_all_values(self) -> list[list[str]]:
            return [
                SHEET_SCHEMAS["Transactions"],
                ["txn_123", "2026-03-23", "expense", "25000", "", "", "Food", "BCA", "", "Cafe", "text", "kopi", "0.95", "confirmed"],
            ]

        def update(self, cell_range: str, values, value_input_option=None) -> None:
            updates.append((cell_range, values))

    client = GoogleSheetsClient(spreadsheet_id="sheet-id", service_account_json='{"type":"service_account"}')
    client._worksheet = lambda name: FakeWorksheet()  # type: ignore[method-assign]
    client._refresh_transaction_date_merges = lambda: None  # type: ignore[method-assign]

    from datetime import date

    from bot_platform.bots.finance.models import TransactionRecord

    client.update_transaction(
        TransactionRecord(
            transaction_id="txn_123",
            transaction_date=date(2026, 3, 23),
            type="expense",
            amount=30000,
            category="Food",
            payment_method="GoPay",
            account_from="GoPay",
            merchant_or_source="Cafe",
        )
    )

    assert updates[0][0] == "A2:N2"


def test_add_payment_method_appends_unique_row() -> None:
    appended_rows: list[list[list[str]]] = []

    class FakeWorksheet:
        def get_all_values(self) -> list[list[str]]:
            return [
                SHEET_SCHEMAS["Categories"],
                ["payment_method", "Payment Method", "GoPay", "", "yes"],
            ]

        def append_rows(self, rows, value_input_option=None) -> None:
            appended_rows.append(rows)

    client = GoogleSheetsClient(spreadsheet_id="sheet-id", service_account_json='{"type":"service_account"}')
    client._worksheet = lambda name: FakeWorksheet()  # type: ignore[method-assign]

    client.add_payment_method("Jenius")

    assert appended_rows == [[["payment_method", "Payment Method", "Jenius", "", "yes"]]]


def test_worksheet_recreates_header_when_sheet_is_empty() -> None:
    calls: list[str] = []

    class FakeWorksheet:
        title = "Transactions"

        def row_values(self, index: int) -> list[str]:
            assert index == 1
            return []

        def append_row(self, values, value_input_option=None) -> None:
            calls.append(",".join(values))

    client = GoogleSheetsClient(spreadsheet_id="sheet-id", service_account_json='{"type":"service_account"}')
    client._spreadsheet = lambda: type("FakeSpreadsheet", (), {"worksheet": lambda _self, name: FakeWorksheet()})()  # type: ignore[method-assign]

    worksheet = client._worksheet("Transactions")

    assert worksheet.title == "Transactions"
    assert calls == [",".join(SHEET_SCHEMAS["Transactions"])]


def test_worksheet_rewrites_wrong_header_when_sheet_header_is_missing_columns() -> None:
    cleared: list[bool] = []
    appended: list[list[str]] = []

    class FakeWorksheet:
        title = "Summary"

        def row_values(self, index: int) -> list[str]:
            assert index == 1
            return ["wrong", "header"]

        def clear(self) -> None:
            cleared.append(True)

        def append_row(self, values, value_input_option=None) -> None:
            appended.append(list(values))

    client = GoogleSheetsClient(spreadsheet_id="sheet-id", service_account_json='{"type":"service_account"}')
    client._spreadsheet = lambda: type("FakeSpreadsheet", (), {"worksheet": lambda _self, name: FakeWorksheet()})()  # type: ignore[method-assign]

    worksheet = client._worksheet("Summary")

    assert worksheet.title == "Summary"
    assert cleared == [True]
    assert appended == [SHEET_SCHEMAS["Summary"]]
