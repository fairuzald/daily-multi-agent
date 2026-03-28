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
- AI extraction
- pending confirmation and correction flows

That is intentional, because save safety matters more than free-form interpretation.

## Useful Tests

```bash
poetry run env PYTHONPATH=src pytest -q tests/test_sheets_gateway.py
```

Run the full suite before claiming finance changes are done:

```bash
poetry run python -m pytest -q
```
