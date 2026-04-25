# Finance Bot Development

## Main Code Areas

- `application/`
- `interfaces/telegram/`
- `infrastructure/sheets_gateway.py`
- `infrastructure/gemini_gateway.py`
- `infrastructure/openrouter_gateway.py`
- `prompts/`

## Parsing Model

The finance bot is not fully AI-only. It mixes:

- deterministic helpers
- learned mappings
- one unified AI extraction path for live finance messages
- pending confirmation and correction flows

That is intentional, because save safety matters more than free-form interpretation.

Current live prompt:

- `prompts/finance_message_extractor.txt`

Important note:

- old split finance prompt files were removed from the live path
- command parsing still exists as a fallback/supplement, but the normal flow is extractor-first
- saved-reply handling is extractor-first too: explicit edit/delete intent updates the existing row, while normal transaction follow-ups can create a new row and inherit missing context from the replied transaction
- deterministic enrichment must not overwrite an inherited date unless the new message actually contains a date signal

## Useful Tests

```bash
poetry run env PYTHONPATH=src pytest -q tests/test_finance_understanding.py tests/test_owner_only_bots.py
```

Run the full suite before claiming finance changes are done:

```bash
poetry run python -m pytest -q
```
