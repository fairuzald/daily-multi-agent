from __future__ import annotations

from dataclasses import asdict, dataclass
from bot_platform.shared.persistence.json_store import JsonKeyValueStore


@dataclass
class BudgetRule:
    scope: str
    period: str
    limit_amount: int
    category: str = ""


@dataclass
class LearnedMapping:
    pattern: str
    category: str = ""
    subcategory: str = ""
    payment_method: str = ""
    learned_from: str = ""


class FinanceRepository:
    BUDGETS_KEY = "finance:budgets"
    LEARNED_MAPPINGS_KEY = "finance:learned_mappings"

    def __init__(self, database_url: str) -> None:
        self.store = JsonKeyValueStore(database_url)

    def list_budget_rules(self) -> list[BudgetRule]:
        payload = self.store.get_value(self.BUDGETS_KEY) or []
        return [BudgetRule(**item) for item in payload]

    def save_budget_rule(self, rule: BudgetRule) -> None:
        rules = self.list_budget_rules()
        rules = [
            item
            for item in rules
            if not (item.scope == rule.scope and item.period == rule.period and item.category == rule.category)
        ]
        rules.append(rule)
        self.store.set_value(self.BUDGETS_KEY, [asdict(item) for item in rules])

    def list_learned_mappings(self) -> list[LearnedMapping]:
        payload = self.store.get_value(self.LEARNED_MAPPINGS_KEY) or []
        return [LearnedMapping(**item) for item in payload]

    def save_learned_mapping(self, mapping: LearnedMapping) -> None:
        mappings = self.list_learned_mappings()
        mappings = [item for item in mappings if item.pattern.lower() != mapping.pattern.lower()]
        mappings.append(mapping)
        self.store.set_value(self.LEARNED_MAPPINGS_KEY, [asdict(item) for item in mappings])
