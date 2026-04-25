from __future__ import annotations

import re
from typing import Any


_UNIT_MULTIPLIERS = {
    "k": 1_000,
    "rb": 1_000,
    "ribu": 1_000,
    "jt": 1_000_000,
    "juta": 1_000_000,
    "mil": 1_000_000,
    "milyar": 1_000_000_000,
    "miliar": 1_000_000_000,
}

_NAMED_AMOUNTS = {
    "goceng": 5_000,
    "ceban": 10_000,
}


def parse_amount_expression(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 else None

    raw = str(value).strip().lower()
    if not raw:
        return None

    direct_named = _NAMED_AMOUNTS.get(raw)
    if direct_named is not None:
        return direct_named

    total = 0.0
    matched_any = False

    for token, amount in _NAMED_AMOUNTS.items():
        count = len(re.findall(rf"\b{re.escape(token)}\b", raw))
        if count:
            total += amount * count
            matched_any = True

    unit_pattern = re.compile(
        r"(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>k|rb|ribu|jt|juta|mil|milyar|miliar)\b",
        flags=re.IGNORECASE,
    )
    for match in unit_pattern.finditer(raw):
        number = _parse_suffix_number(match.group("number"))
        if number is None:
            continue
        total += number * _UNIT_MULTIPLIERS[match.group("unit").lower()]
        matched_any = True

    if matched_any:
        remainder = unit_pattern.sub(" ", raw)
        for token in _NAMED_AMOUNTS:
            remainder = re.sub(rf"\b{re.escape(token)}\b", " ", remainder)
        remainder = re.sub(r"\s+", " ", remainder).strip(" ,.")
        if not re.search(r"\d", remainder):
            return int(total) if total > 0 else None

    digits_only = re.sub(r"[^\d]", "", raw)
    if digits_only:
        parsed = int(digits_only)
        return parsed if parsed > 0 else None

    return int(total) if total > 0 else None


def _parse_suffix_number(value: str) -> float | None:
    normalized = value.strip().replace(",", ".")
    if normalized.count(".") > 1:
        normalized = normalized.replace(".", "")
    try:
        return float(normalized)
    except ValueError:
        return None
