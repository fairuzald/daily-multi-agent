from __future__ import annotations

import json
from collections.abc import Iterable

from bot_platform.bots.finance.models import MonthlySummary, TransactionRecord


SHEET_SCHEMAS: dict[str, list[str]] = {
    "Transactions": [
        "Transaction ID",
        "Transaction Date",
        "Type",
        "Amount",
        "Subcategory",
        "Description",
        "Category",
        "Payment Method",
        "Destination Account / Wallet",
        "Merchant / Source",
        "Input Mode",
        "Raw Input",
        "AI Confidence",
        "Status",
        "Transaction Group ID",
        "Group Total Amount",
    ],
    "Categories": [
        "Type",
        "Category",
        "Subcategory",
        "Keywords",
        "Active",
    ],
    "Summary": ["Section", "Month", "Label", "Value", "Details"],
}


class GoogleSheetsClient:
    def __init__(self, spreadsheet_id: str, service_account_json: str = "") -> None:
        self.spreadsheet_id = spreadsheet_id
        self.service_account_json = service_account_json

    def append_transaction(self, transaction: TransactionRecord) -> None:
        worksheet = self._worksheet("Transactions")
        worksheet.append_row(transaction.to_row(), value_input_option="USER_ENTERED")
        self._refresh_transaction_merges()

    def append_transactions(self, transactions: list[TransactionRecord]) -> None:
        if not transactions:
            return
        worksheet = self._worksheet("Transactions")
        worksheet.append_rows([item.to_row() for item in transactions], value_input_option="USER_ENTERED")
        self._refresh_transaction_merges()

    def read_transactions(self) -> list[dict[str, str]]:
        return self._worksheet("Transactions").get_all_records()

    def update_transaction(self, transaction: TransactionRecord) -> None:
        worksheet = self._worksheet("Transactions")
        rows = worksheet.get_all_values()
        for index, row in enumerate(rows[1:], start=2):
            if row and len(row) >= 1 and row[0] == transaction.transaction_id:
                worksheet.update(f"A{index}:P{index}", [transaction.to_row()], value_input_option="USER_ENTERED")
                self._refresh_transaction_merges()
                return
        raise ValueError(f"Transaction {transaction.transaction_id} was not found in the sheet")

    def replace_categories(self, rows: list[list[str]]) -> None:
        worksheet = self._worksheet("Categories")
        worksheet.clear()
        for chunk in chunk_rows(rows):
            worksheet.append_rows(chunk, value_input_option="USER_ENTERED")

    def ensure_default_categories(self, rows: list[list[str]]) -> None:
        worksheet = self._worksheet("Categories")
        existing_rows = worksheet.get_all_values()
        if len(existing_rows) <= 1:
            self.replace_categories(rows)
            return
        self._append_missing_category_rows(worksheet, rows[1:])

    def add_category(self, tx_type: str, category: str, subcategory: str) -> None:
        worksheet = self._worksheet("Categories")
        self._append_missing_category_rows(worksheet, [[tx_type, category, subcategory, "", "yes"]])

    def add_payment_method(self, payment_method: str) -> None:
        worksheet = self._worksheet("Categories")
        self._append_missing_category_rows(worksheet, [["payment_method", "Payment Method", payment_method, "", "yes"]])

    def replace_summary(self, summary: MonthlySummary) -> None:
        worksheet = self._worksheet("Summary")
        rows = [SHEET_SCHEMAS["Summary"]]
        overview = summary.overview
        rows.extend(
            [
                ["Overview", overview.month, "Total Income", overview.total_income, ""],
                ["Overview", overview.month, "Total Expense", overview.total_expense, ""],
                ["Overview", overview.month, "Total Transfer", overview.total_transfer, ""],
                ["Overview", overview.month, "Net Cash Flow", overview.net_cash_flow, ""],
                ["Overview", overview.month, "Savings Rate", overview.savings_rate, ""],
                ["Overview", overview.month, "Largest Expense Category", overview.largest_expense_category, ""],
                ["Overview", overview.month, "Largest Income Source", overview.largest_income_source, ""],
            ]
        )
        for item in summary.expense_categories:
            rows.append(
                [
                    "Spending by Category",
                    item.month,
                    item.category,
                    item.total_amount,
                    f"{item.percent_of_total_expense * 100:.1f}% of expense",
                ]
            )
        for item in summary.income_sources:
            rows.append(["Income Sources", item.month, item.source, item.total_amount, f"{item.percent_of_total_income * 100:.1f}%"])
        for item in summary.account_balances:
            rows.append(
                [
                    "Spending by Payment Method",
                    overview.month,
                    item.account_name,
                    item.closing_balance,
                    f"Inflow {item.inflow} / Outflow {item.outflow}",
                ]
            )
        for item in summary.insights:
            rows.append(["Improvement Insights", item.month, item.insight_type, item.priority, item.insight_text])
        worksheet.clear()
        worksheet.update(rows)

    def ensure_schema(self) -> None:
        spreadsheet = self._spreadsheet()
        worksheets = spreadsheet.worksheets()
        existing = {sheet.title for sheet in worksheets}
        for name, headers in SHEET_SCHEMAS.items():
            if name not in existing:
                worksheet = spreadsheet.add_worksheet(title=name, rows=200, cols=max(10, len(headers) + 2))
                worksheet.append_row(headers)
                continue
            worksheet = spreadsheet.worksheet(name)
            current = worksheet.row_values(1)
            if current != headers:
                self._write_header_row(worksheet, headers, current)

    def _spreadsheet(self):
        try:
            import gspread
        except ImportError as exc:
            raise RuntimeError("gspread is not installed. Run `poetry install` first.") from exc
        credentials = self._credentials_config()
        client = gspread.service_account_from_dict(credentials)
        return client.open_by_key(self.spreadsheet_id)

    def _worksheet(self, name: str):
        worksheet = self._spreadsheet().worksheet(name)
        expected_header = SHEET_SCHEMAS.get(name)
        if expected_header:
            current_header = worksheet.row_values(1)
            if not current_header:
                worksheet.append_row(expected_header)
            elif current_header != expected_header:
                self._write_header_row(worksheet, expected_header, current_header)
        return worksheet

    def _write_header_row(self, worksheet, headers: list[str], current_header: list[str]) -> None:
        if not current_header:
            worksheet.append_row(headers)
            return
        end_column = self._column_label(len(headers))
        worksheet.update(f"A1:{end_column}1", [headers], value_input_option="USER_ENTERED")

    def _refresh_transaction_merges(self) -> None:
        spreadsheet = self._spreadsheet()
        worksheet = spreadsheet.worksheet("Transactions")
        values = worksheet.get_all_values()

        metadata = spreadsheet.fetch_sheet_metadata()
        sheet_meta = next(sheet for sheet in metadata["sheets"] if sheet["properties"]["title"] == "Transactions")
        sheet_id = sheet_meta["properties"]["sheetId"]
        existing_merges = list(sheet_meta.get("merges", []))
        requests = self._build_transaction_merge_update_requests(
            sheet_id=sheet_id,
            rows=values,
            existing_merges=existing_merges,
        )

        if requests:
            spreadsheet.batch_update({"requests": requests})

    @classmethod
    def _build_transaction_merge_update_requests(
        cls,
        *,
        sheet_id: int,
        rows: list[list[str]],
        existing_merges: list[dict[str, int]],
    ) -> list[dict[str, object]]:
        requests: list[dict[str, object]] = [
            {
                "unmergeCells": {
                    "range": dict(merge_range),
                }
            }
            for merge_range in existing_merges
        ]

        if len(rows) <= 2:
            return requests

        group_values = [row[14] if len(row) > 14 else "" for row in rows]
        merge_requests: list[dict[str, object]] = []
        for column_index in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15):
            merge_requests.extend(
                cls._build_group_merge_requests(
                    sheet_id=sheet_id,
                    rows=rows,
                    group_values=group_values,
                    column_index=column_index,
                )
            )

        requests.extend(merge_requests)
        merged_ranges = [dict(request["mergeCells"]["range"]) for request in merge_requests if "mergeCells" in request]
        requests.extend(cls._build_center_alignment_requests(merged_ranges))
        return requests

    @classmethod
    def _build_center_alignment_requests(cls, merge_ranges: list[dict[str, int]]) -> list[dict[str, object]]:
        requests: list[dict[str, object]] = []
        for merge_range in merge_ranges:
            requests.append(
                {
                    "repeatCell": {
                        "range": dict(merge_range),
                        "cell": {
                            "userEnteredFormat": {
                                "verticalAlignment": "MIDDLE",
                            }
                        },
                        "fields": "userEnteredFormat.verticalAlignment",
                    }
                }
            )
        return requests

    @staticmethod
    def _build_merge_requests(
        *,
        sheet_id: int,
        values: list[str],
        start_column_index: int,
        end_column_index: int,
    ) -> list[dict[str, object]]:
        if len(values) <= 2:
            return []

        requests: list[dict[str, object]] = []
        start = 1
        current = values[1]
        for index in range(2, len(values) + 1):
            next_value = values[index] if index < len(values) else None
            if next_value != current:
                if current and index - start > 1:
                    requests.append(
                        {
                            "mergeCells": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": start,
                                    "endRowIndex": index,
                                    "startColumnIndex": start_column_index,
                                    "endColumnIndex": end_column_index,
                                },
                                "mergeType": "MERGE_ALL",
                            }
                        }
                    )
                start = index
                current = next_value
        return requests

    @staticmethod
    def _build_group_merge_requests(
        *,
        sheet_id: int,
        rows: list[list[str]],
        group_values: list[str],
        column_index: int,
    ) -> list[dict[str, object]]:
        if len(rows) <= 2:
            return []

        requests: list[dict[str, object]] = []
        start: int | None = None
        current_group = ""
        current_value = ""
        for index in range(1, len(rows)):
            row = rows[index]
            group_id = row[14] if len(row) > 14 else ""
            value = row[column_index] if len(row) > column_index else ""
            if not group_id or not value:
                if start is not None and index - start > 1:
                    requests.append(
                        {
                            "mergeCells": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": start,
                                    "endRowIndex": index,
                                    "startColumnIndex": column_index,
                                    "endColumnIndex": column_index + 1,
                                },
                                "mergeType": "MERGE_ALL",
                            }
                        }
                    )
                start = None
                current_group = ""
                current_value = ""
                continue
            if start is None:
                start = index
                current_group = group_id
                current_value = value
                continue
            if group_id != current_group or value != current_value:
                if index - start > 1:
                    requests.append(
                        {
                            "mergeCells": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": start,
                                    "endRowIndex": index,
                                    "startColumnIndex": column_index,
                                    "endColumnIndex": column_index + 1,
                                },
                                "mergeType": "MERGE_ALL",
                            }
                        }
                    )
                start = index
                current_group = group_id
                current_value = value
        if start is not None and len(rows) - start > 1:
            requests.append(
                {
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": start,
                            "endRowIndex": len(rows),
                            "startColumnIndex": column_index,
                            "endColumnIndex": column_index + 1,
                        },
                        "mergeType": "MERGE_ALL",
                    }
                }
            )
        return requests

    @staticmethod
    def _reconcile_merge_requests(
        requests: list[dict[str, object]],
        *,
        existing_merges: list[dict[str, int]],
    ) -> tuple[list[dict[str, object]], list[dict[str, int]]]:
        output_requests: list[dict[str, object]] = []
        aligned_ranges: list[dict[str, int]] = []
        seen_ranges = [dict(item) for item in existing_merges]
        for request in requests:
            merge_request = request.get("mergeCells", {})
            merge_range = merge_request.get("range", {})
            if not merge_range:
                continue
            exact_match = next((existing for existing in seen_ranges if GoogleSheetsClient._ranges_equal(merge_range, existing)), None)
            if exact_match is not None:
                continue
            extendable_match = next(
                (
                    existing
                    for existing in seen_ranges
                    if GoogleSheetsClient._can_replace_merge(existing, merge_range)
                ),
                None,
            )
            if extendable_match is not None:
                output_requests.append({"unmergeCells": {"range": dict(extendable_match)}})
                output_requests.append(request)
                aligned_ranges.append(dict(merge_range))
                seen_ranges.remove(extendable_match)
                seen_ranges.append(dict(merge_range))
                continue
            if any(GoogleSheetsClient._ranges_overlap(merge_range, existing) for existing in seen_ranges):
                continue
            output_requests.append(request)
            aligned_ranges.append(dict(merge_range))
            seen_ranges.append(dict(merge_range))
        return output_requests, aligned_ranges

    @staticmethod
    def _ranges_overlap(left: dict[str, int], right: dict[str, int]) -> bool:
        if left.get("sheetId") != right.get("sheetId"):
            return False
        row_overlap = left["startRowIndex"] < right["endRowIndex"] and right["startRowIndex"] < left["endRowIndex"]
        column_overlap = left["startColumnIndex"] < right["endColumnIndex"] and right["startColumnIndex"] < left["endColumnIndex"]
        return row_overlap and column_overlap

    @staticmethod
    def _ranges_equal(left: dict[str, int], right: dict[str, int]) -> bool:
        return (
            left.get("sheetId") == right.get("sheetId")
            and left.get("startRowIndex") == right.get("startRowIndex")
            and left.get("endRowIndex") == right.get("endRowIndex")
            and left.get("startColumnIndex") == right.get("startColumnIndex")
            and left.get("endColumnIndex") == right.get("endColumnIndex")
        )

    @staticmethod
    def _can_replace_merge(existing: dict[str, int], candidate: dict[str, int]) -> bool:
        if existing.get("sheetId") != candidate.get("sheetId"):
            return False
        if existing.get("startColumnIndex") != candidate.get("startColumnIndex"):
            return False
        if existing.get("endColumnIndex") != candidate.get("endColumnIndex"):
            return False
        return (
            candidate["startRowIndex"] <= existing["startRowIndex"]
            and candidate["endRowIndex"] >= existing["endRowIndex"]
            and not GoogleSheetsClient._ranges_equal(existing, candidate)
        )

    def _credentials_config(self) -> dict[str, str]:
        if not self.service_account_json.strip():
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is missing")
        try:
            parsed = json.loads(self.service_account_json)
        except json.JSONDecodeError as exc:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON must decode to a JSON object")
        return parsed

    @staticmethod
    def _append_missing_category_rows(worksheet, rows: list[list[str]]) -> None:
        existing_values = worksheet.get_all_values()
        existing_keys = {tuple(row[:3]) for row in existing_values[1:] if len(row) >= 3}
        new_rows = [row for row in rows if tuple(row[:3]) not in existing_keys]
        if new_rows:
            worksheet.append_rows(new_rows, value_input_option="USER_ENTERED")

    @staticmethod
    def _column_label(index: int) -> str:
        if index <= 0:
            raise ValueError("column index must be positive")
        label = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            label = chr(65 + remainder) + label
        return label


def build_category_rows(category_map: dict[str, dict[str, list[str]]]) -> list[list[str]]:
    rows: list[list[str]] = [SHEET_SCHEMAS["Categories"]]
    for tx_type, groups in category_map.items():
        for category, subcategories in groups.items():
            for subcategory in subcategories:
                rows.append([tx_type, category, subcategory, "", "yes"])
    return rows


def chunk_rows(rows: Iterable[list[str]], chunk_size: int = 500) -> list[list[list[str]]]:
    chunk: list[list[str]] = []
    chunks: list[list[list[str]]] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) == chunk_size:
            chunks.append(chunk)
            chunk = []
    if chunk:
        chunks.append(chunk)
    return chunks
