# Life Bot Development

## Main Code Areas

- `application/life_bot_service.py`
- `domain/parser.py`
- `infrastructure/gemini_gateway.py`
- `infrastructure/openrouter_gateway.py`
- `infrastructure/state_store.py`
- `prompts/`

## Parsing Model

The life bot is AI-first:

- AI uses one unified extractor prompt to interpret one or more items, including rewrites
- if output is safe, items are saved immediately
- if output is unsafe or providers fail, the bot stores a pending rewrite state
- the user can reply naturally with a clearer sentence

Deterministic parsing still exists as a fallback when no AI client is configured.

## Reply Context

Reply contexts are used for two different flows:

- item actions like `/done` and `/snooze`
- pending rewrite prompts after failed parsing

## Useful Tests

```bash
poetry run env PYTHONPATH=src pytest -q tests/test_life_bot.py
```

Run compile checks after touching the life bot AI gateways or controller:

```bash
python -m compileall src/bot_platform/bots/life src/bot_platform/shared/bootstrap/factory.py api/telegram_webhook.py
```
