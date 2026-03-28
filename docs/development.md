# Development

This repo runs both bots through the same FastAPI webhook app.

## Main Targets

```bash
make install
make test
make local-dev
make local-prod
make ngrok-dev
make webhook-set-dev
make BOT=2 webhook-set-dev
make docker-dev
make docker-logs-dev
make docker-down
```

## Local Run

```bash
make local-dev
```

This starts:

- `api/telegram_webhook.py`
- finance webhook at `/api/telegram_webhook`
- life webhook at `/api/life_telegram_webhook`
- life reminder tick at `/api/life_reminder_tick`

## Local Webhook Flow

1. Start the app with `make local-dev`
2. Expose it with `make ngrok-dev`
3. Set the webhook you want:

Finance:

```bash
make webhook-set-dev
```

Life:

```bash
make BOT=2 webhook-set-dev
```

## Testing

Full suite:

```bash
poetry run python -m pytest -q
```

Targeted:

```bash
poetry run env PYTHONPATH=src pytest -q tests/test_life_bot.py tests/test_sheets_gateway.py
```

## AI Development Notes

Finance bot:

- deterministic helpers plus AI parsing
- review flows for low-confidence results

Life bot:

- AI-first parsing for natural language
- supports one message producing multiple items
- falls back to pending rewrite mode when parsing is unsafe
- deterministic parser is still kept as a no-AI fallback

## Bot-Specific Development Docs

- Finance: [src/bot_platform/bots/finance/DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/DEVELOPMENT.md)
- Life: [src/bot_platform/bots/life/DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/DEVELOPMENT.md)
