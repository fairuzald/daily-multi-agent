from bot_platform.shared.config.settings import Settings


def test_validate_google_required_allows_bootstrap_without_telegram_or_gemini() -> None:
    settings = Settings(
        telegram_bot_token="",
        gemini_api_key="",
        database_url="",
        google_sheet_id="sheet-id",
        google_service_account_json='{"type":"service_account"}',
    )

    assert settings.validate_google_required() == []
