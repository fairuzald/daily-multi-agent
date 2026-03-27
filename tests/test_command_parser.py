from bot_platform.bots.finance.domain.command_parser import CommandParser


def test_command_parser_detects_delete() -> None:
    parser = CommandParser()

    command = parser.parse("delete this")

    assert command.intent == "delete"
    assert command.target == "reply"


def test_command_parser_detects_budget_set() -> None:
    parser = CommandParser()

    command = parser.parse("set monthly food budget 500000")

    assert command.intent == "budget_set"
    assert command.period == "monthly"
    assert command.amount == 500000


def test_command_parser_detects_compare_month() -> None:
    parser = CommandParser()

    command = parser.parse("compare this month with last month")

    assert command.intent == "compare_month"
