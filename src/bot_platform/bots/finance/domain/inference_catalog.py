from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class KeywordCategoryRule:
    category: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class TransactionInferenceRuleSet:
    default_category: str
    keyword_categories: tuple[KeywordCategoryRule, ...] = ()
    default_subcategory: str = ""
    default_description: str = ""
    default_description_suffix: str = ""

    def category_for(self, haystack: str) -> str | None:
        for rule in self.keyword_categories:
            if any(keyword in haystack for keyword in rule.keywords):
                return rule.category
        return None


@dataclass(frozen=True)
class TransactionInferenceCatalog:
    income: TransactionInferenceRuleSet
    investment_in: TransactionInferenceRuleSet
    investment_out: TransactionInferenceRuleSet
    expense: TransactionInferenceRuleSet


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "inference_rules.json"


def _parse_rule_set(raw: dict[str, object]) -> TransactionInferenceRuleSet:
    keyword_categories = tuple(
        KeywordCategoryRule(
            category=str(item["category"]),
            keywords=tuple(str(keyword) for keyword in item.get("keywords", [])),
        )
        for item in raw.get("keyword_categories", [])
        if isinstance(item, dict) and item.get("category")
    )
    return TransactionInferenceRuleSet(
        default_category=str(raw.get("default_category") or ""),
        keyword_categories=keyword_categories,
        default_subcategory=str(raw.get("default_subcategory") or ""),
        default_description=str(raw.get("default_description") or ""),
        default_description_suffix=str(raw.get("default_description_suffix") or ""),
    )


@lru_cache(maxsize=1)
def load_inference_catalog() -> TransactionInferenceCatalog:
    path = _config_path()
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise RuntimeError("Finance inference catalog must be a JSON object.")
    return TransactionInferenceCatalog(
        income=_parse_rule_set(dict(raw.get("income") or {})),
        investment_in=_parse_rule_set(dict(raw.get("investment_in") or {})),
        investment_out=_parse_rule_set(dict(raw.get("investment_out") or {})),
        expense=_parse_rule_set(dict(raw.get("expense") or {})),
    )
