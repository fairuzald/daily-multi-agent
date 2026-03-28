from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MultiTransactionCandidate:
    kind: str
    raw_input: str
    item_inputs: list[str]
    item_labels: list[str]
    shared_total_amount: int | None = None


def detect_multi_transaction(raw_text: str) -> MultiTransactionCandidate | None:
    text = " ".join(raw_text.strip().split())
    if not text:
        return None

    payment_phrase, body = _extract_trailing_payment_phrase(text)
    clauses = [part.strip(" ,.") for part in re.split(r"\s+dan\s+", body, flags=re.IGNORECASE) if part.strip(" ,.")] 
    if len(clauses) < 2:
        return None

    date_phrase = _extract_leading_date_phrase(text)
    verb = _extract_shared_verb(text)
    shared_context, first_item = _extract_shared_context_and_first_item(clauses[0], date_phrase=date_phrase, verb=verb)
    cleaned_clauses = [first_item] + [_strip_shared_total_phrase(part.strip()) for part in clauses[1:]]
    cleaned_clauses = [part for part in cleaned_clauses if part]
    if len(cleaned_clauses) < 2:
        return None

    explicit_amounts = [_extract_last_amount(part) for part in cleaned_clauses]
    if all(amount is not None for amount in explicit_amounts):
        item_inputs = [_build_item_input(date_phrase, verb, shared_context, part, payment_phrase) for part in cleaned_clauses]
        return MultiTransactionCandidate(
            kind="explicit",
            raw_input=raw_text,
            item_inputs=item_inputs,
            item_labels=[_strip_amount(part) for part in cleaned_clauses],
        )

    all_amounts = re.findall(r"\d[\d\.]*", body)
    if len(all_amounts) == 1 and re.search(r"\b(?:seharga|harga|total(?:nya)?|senilai)\b", body, flags=re.IGNORECASE):
        shared_total_amount = _parse_amount(all_amounts[0])
        if shared_total_amount is None:
            return None
        item_inputs = [_build_item_input(date_phrase, verb, shared_context, part, payment_phrase) for part in cleaned_clauses]
        return MultiTransactionCandidate(
            kind="ambiguous",
            raw_input=raw_text,
            item_inputs=item_inputs,
            item_labels=[_strip_amount(part) for part in cleaned_clauses],
            shared_total_amount=shared_total_amount,
        )

    return None


def parse_group_allocation_reply(message_text: str, expected_count: int, shared_total_amount: int) -> list[int] | None:
    amounts = [_parse_amount(match) for match in re.findall(r"\d[\d\.]*", message_text)]
    if len(amounts) != expected_count or any(amount is None for amount in amounts):
        return None
    parsed_amounts = [int(amount) for amount in amounts if amount is not None]
    if sum(parsed_amounts) != shared_total_amount:
        return None
    return parsed_amounts


def even_split_amounts(total_amount: int, item_count: int) -> list[int]:
    base_amount = total_amount // item_count
    remainder = total_amount % item_count
    allocations = [base_amount] * item_count
    for index in range(remainder):
        allocations[index] += 1
    return allocations


def _extract_trailing_payment_phrase(text: str) -> tuple[str, str]:
    match = re.search(r"\b(pakai|via|dengan|gunakan)\s+[a-zA-Z0-9][a-zA-Z0-9\s-]*$", text, flags=re.IGNORECASE)
    if not match:
        return "", text
    return text[match.start():].strip(), text[:match.start()].strip(" ,.")


def _extract_leading_date_phrase(text: str) -> str:
    match = re.match(
        r"^\s*((?:hari ini|kemarin|barusan|tadi|\d{4}-\d{2}-\d{2}|[0-9]+\s+hari\s+lalu))\b[:, ]*",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _extract_shared_verb(text: str) -> str:
    match = re.search(r"\b(beli|membeli|pesan|order|bayar|makan|minum)\b", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_shared_context_and_first_item(clause: str, *, date_phrase: str, verb: str) -> tuple[str, str]:
    value = clause.strip()
    marker_match = re.search(r"\b(?:yaitu|berupa)\b\s+(.*)$", value, flags=re.IGNORECASE)
    if marker_match:
        prefix = value[:marker_match.start()].strip(" ,.")
        shared_context = _strip_leading_context(prefix, date_phrase=date_phrase, verb=verb)
        return shared_context, marker_match.group(1).strip()

    cleaned = _strip_shared_total_phrase(value)
    verb_match = re.search(r"\b(?:saya|aku)?\s*(?:beli|membeli|pesan|order|bayar|makan|minum)\b\s+(.*)$", cleaned, flags=re.IGNORECASE)
    if verb_match:
        return "", verb_match.group(1).strip()
    return "", cleaned


def _build_item_input(date_phrase: str, verb: str, shared_context: str, clause: str, payment_phrase: str) -> str:
    cleaned_clause = clause.strip()
    parts: list[str] = []
    if date_phrase:
        parts.append(date_phrase)
    lowered_clause = cleaned_clause.lower()
    if verb and not lowered_clause.startswith(verb.lower()):
        parts.append(verb)
    if shared_context and shared_context.lower() not in lowered_clause:
        parts.append(shared_context)
    parts.append(cleaned_clause)
    if payment_phrase and payment_phrase.lower() not in lowered_clause:
        parts.append(payment_phrase)
    return " ".join(part for part in parts if part).strip()


def _extract_last_amount(text: str) -> int | None:
    matches = re.findall(r"\d[\d\.]*", text)
    if not matches:
        return None
    return _parse_amount(matches[-1])


def _strip_amount(text: str) -> str:
    return re.sub(r"\s*\d[\d\.]*\s*$", "", text).strip(" ,.")


def _strip_shared_total_phrase(text: str) -> str:
    return re.sub(r"\b(?:seharga|harga|total(?:nya)?|senilai)\b\s*\d[\d\.]*(?:\s*[a-zA-Z]*)?$", "", text, flags=re.IGNORECASE).strip(" ,.")


def _strip_leading_context(text: str, *, date_phrase: str, verb: str) -> str:
    value = text.strip(" ,.")
    if date_phrase and value.lower().startswith(date_phrase.lower()):
        value = value[len(date_phrase):].strip(" ,.")
    value = re.sub(r"^(?:saya|aku)\b", "", value, flags=re.IGNORECASE).strip(" ,.")
    if verb:
        value = re.sub(rf"^{re.escape(verb)}\b", "", value, flags=re.IGNORECASE).strip(" ,.")
    return value.strip(" ,.")


def _parse_amount(text: str) -> int | None:
    digits = "".join(char for char in text if char.isdigit())
    return int(digits) if digits else None
