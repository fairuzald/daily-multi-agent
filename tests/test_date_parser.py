from datetime import datetime, timezone

from bot_platform.bots.finance.domain.date_parser import DateParser


def test_date_parser_defaults_to_message_date_when_no_phrase() -> None:
    parser = DateParser("Asia/Jakarta")

    resolution = parser.resolve(
        "beli kopi 25000 pakai bca",
        message_datetime=datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc),
    )

    assert resolution.ambiguous is False
    assert resolution.resolved_date.isoformat() == "2026-03-27"


def test_date_parser_handles_relative_indonesian_phrase() -> None:
    parser = DateParser("Asia/Jakarta")

    resolution = parser.resolve(
        "kemarin beli makan 50000",
        message_datetime=datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc),
    )

    assert resolution.resolved_date.isoformat() == "2026-03-26"


def test_date_parser_marks_multiple_dates_as_ambiguous() -> None:
    parser = DateParser("Asia/Jakarta")

    resolution = parser.resolve(
        "beli kopi kemarin 2026-03-20",
        message_datetime=datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc),
    )

    assert resolution.ambiguous is True
    assert resolution.resolved_date is None
