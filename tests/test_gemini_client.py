from datetime import date

from bot_platform.bots.finance.infrastructure.gemini_gateway import GeminiClient


def test_gemini_client_initialization_loads_prompt_assets() -> None:
    client = GeminiClient(api_key="test-key")

    assert "structured JSON transaction" in client._transaction_prompt
    assert "transaction correction parser" in client._correction_prompt
    assert "Indonesian Telegram images" in client._image_prompt


def test_extract_json_text_removes_markdown_fences() -> None:
    raw = """```json
{
  "type": "expense",
  "amount": 25000
}
```"""

    assert GeminiClient._extract_json_text(raw) == '{\n  "type": "expense",\n  "amount": 25000\n}'


def test_normalize_payload_handles_nulls_and_relative_date() -> None:
    payload = {
        "type": "expense",
        "amount": 25000,
        "currency": "IDR",
        "transaction_date": "today",
        "category": "Food",
        "subcategory": "Coffee",
        "account_from": "BCA",
        "account_to": None,
        "merchant_or_source": None,
        "description": "Pembelian kopi",
        "payment_method": None,
        "tags": None,
        "raw_input": "beli kopi 25000 pakai bca",
        "confidence": 0.85,
        "needs_confirmation": True,
        "missing_fields": None,
    }

    normalized = GeminiClient._normalize_payload(payload)

    assert normalized["transaction_date"] == date.today().isoformat()
    assert normalized["account_to"] == ""
    assert normalized["merchant_or_source"] == ""
    assert normalized["payment_method"] == "BCA"
    assert normalized["tags"] == []
    assert normalized["missing_fields"] == []
    assert normalized["needs_confirmation"] is True


def test_normalize_payload_treats_merchant_as_optional() -> None:
    payload = {
        "type": "expense",
        "amount": 16000,
        "currency": "IDR",
        "transaction_date": None,
        "category": "Food",
        "subcategory": "Coffee",
        "account_from": None,
        "account_to": None,
        "merchant_or_source": None,
        "description": "beli kopi",
        "payment_method": None,
        "tags": [],
        "raw_input": "beli kopi 16000",
        "confidence": 0.75,
        "needs_confirmation": True,
        "missing_fields": ["transaction_date", "account_from", "merchant_or_source", "payment_method"],
    }

    normalized = GeminiClient._normalize_payload(payload)

    assert "merchant_or_source" not in normalized["missing_fields"]
    assert "account_from" not in normalized["missing_fields"]
    assert "payment_method" in normalized["missing_fields"]


def test_normalize_payload_requires_type_when_missing() -> None:
    payload = {
        "type": None,
        "amount": 10000,
        "currency": "IDR",
        "transaction_date": None,
        "category": "Food",
        "subcategory": "",
        "account_from": "",
        "account_to": "",
        "merchant_or_source": "",
        "description": "kopi",
        "payment_method": "",
        "tags": [],
        "raw_input": "kopi sepuluh ribu",
        "confidence": 0.5,
        "needs_confirmation": True,
        "missing_fields": [],
    }

    normalized = GeminiClient._normalize_payload(payload)

    assert normalized["missing_fields"][0] == "type"


def test_normalize_payload_keeps_existing_raw_input_for_image_fallback() -> None:
    payload = {
        "type": "expense",
        "amount": 450000,
        "currency": "IDR",
        "transaction_date": "today",
        "category": "Bills",
        "subcategory": "Electricity",
        "account_from": "GoPay",
        "account_to": "",
        "merchant_or_source": "PLN",
        "description": "bill payment",
        "payment_method": "QRIS",
        "tags": [],
        "raw_input": "",
        "confidence": 0.9,
        "needs_confirmation": False,
        "missing_fields": [],
    }

    normalized = GeminiClient._normalize_payload(payload)

    assert normalized["transaction_date"] == date.today().isoformat()
    assert normalized["raw_input"] == ""


def test_normalize_payload_turns_zero_amount_into_missing_amount() -> None:
    payload = {
        "type": "expense",
        "amount": 0,
        "currency": "IDR",
        "transaction_date": "today",
        "category": "Food",
        "subcategory": "",
        "account_from": "BRI",
        "account_to": "",
        "merchant_or_source": "Jabarano",
        "description": "receipt",
        "payment_method": "QRIS",
        "tags": [],
        "raw_input": "image transaction proof",
        "confidence": 0.85,
        "needs_confirmation": False,
        "missing_fields": [],
    }

    normalized = GeminiClient._normalize_payload(payload)

    assert normalized["amount"] is None
    assert "amount" in normalized["missing_fields"]
    assert normalized["needs_confirmation"] is True


def test_normalize_payload_clears_account_to_for_non_transfer() -> None:
    payload = {
        "type": "expense",
        "amount": 152000,
        "currency": "IDR",
        "transaction_date": "today",
        "category": "Food",
        "subcategory": "Coffee",
        "account_from": "BRI",
        "account_to": "Jabarano",
        "merchant_or_source": "Jabarano Coffee",
        "description": "receipt",
        "payment_method": "QRIS",
        "tags": [],
        "raw_input": "image transaction proof",
        "confidence": 0.91,
        "needs_confirmation": False,
        "missing_fields": [],
    }

    normalized = GeminiClient._normalize_payload(payload)

    assert normalized["account_to"] == ""


def test_normalize_payload_maps_specific_wallet_names() -> None:
    payload = {
        "type": "expense",
        "amount": 38000,
        "currency": "IDR",
        "transaction_date": "today",
        "category": "Food",
        "subcategory": "Coffee",
        "account_from": "ewallet",
        "account_to": "",
        "merchant_or_source": "Tomoro Coffee",
        "description": "Pembelian kopi di Tomoro Coffee pakai gopay",
        "payment_method": "e-wallet",
        "tags": [],
        "raw_input": "pakai gopay",
        "confidence": 0.91,
        "needs_confirmation": False,
        "missing_fields": [],
    }

    normalized = GeminiClient._normalize_payload(payload)

    assert normalized["payment_method"] == "GoPay"
    assert normalized["account_from"] == "GoPay"


def test_normalize_payment_method_maps_bank_names() -> None:
    assert GeminiClient._normalize_payment_method("bca") == "BCA"
    assert GeminiClient._normalize_payment_method("bri mobile") == "BRI"
    assert GeminiClient._normalize_payment_method("shopee pay") == "ShopeePay"
    assert GeminiClient._normalize_payment_method("qris") == "QRIS"
    assert GeminiClient._normalize_payment_method("bank transfer") == "Bank Transfer"
    assert GeminiClient._normalize_payment_method("e-wallet") == "E-Wallet"
    assert GeminiClient._normalize_payment_method("e-wallet", raw_context="pembayaran pakai dana") == "DANA"


def test_normalize_payload_coerces_datetime_string_to_date() -> None:
    payload = {
        "type": "expense",
        "amount": 157500,
        "currency": "IDR",
        "transaction_date": "2026-02-21T16:11:24",
        "category": "",
        "subcategory": "",
        "account_from": "BCA",
        "account_to": "",
        "merchant_or_source": "NAMU BERSIH SEJAHTER",
        "description": "Transfer to NAMU BERSIH SEJAHTER",
        "payment_method": "BCA",
        "tags": [],
        "raw_input": "image transaction proof",
        "confidence": 0.88,
        "needs_confirmation": True,
        "missing_fields": ["subcategory"],
    }

    normalized = GeminiClient._normalize_payload(payload)

    assert normalized["transaction_date"] == "2026-02-21"


def test_normalize_payload_replaces_placeholder_date_with_safe_default() -> None:
    payload = {
        "type": "expense",
        "amount": 25000,
        "currency": "IDR",
        "transaction_date": "YYYY-MM-DD",
        "category": "Food",
        "subcategory": "Coffee",
        "account_from": "BCA",
        "account_to": "",
        "merchant_or_source": "",
        "description": "kopi",
        "payment_method": "BCA",
        "tags": [],
        "raw_input": "beli kopi 25000",
        "confidence": 0.7,
        "needs_confirmation": False,
        "missing_fields": [],
    }

    normalized = GeminiClient._normalize_payload(payload)

    assert normalized["transaction_date"] == date.today().isoformat()
    assert normalized["needs_confirmation"] is True
