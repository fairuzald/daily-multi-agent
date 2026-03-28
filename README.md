# Bot Platform

Private Telegram bot platform for one-owner workflows. The repo currently contains two bots:

- `Finance Bot` for expense tracking into Google Sheets
- `Life Bot` for tasks, reminders, follow-ups, important dates, and Google Calendar sync

Both bots share the same runtime patterns:

- Telegram webhook via FastAPI
- Postgres-backed state store
- provider-routed AI
- owner-only access control

## Bots

### Finance Bot

Main product flow:

- parse Indonesian text, voice notes, and screenshots
- store structured transactions in Google Sheets
- support reply-based review, correction, deletion, budgets, and summaries

Docs:

- Product: [src/bot_platform/bots/finance/README.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/README.md)
- Setup: [src/bot_platform/bots/finance/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/SETUP.md)
- Development: [src/bot_platform/bots/finance/DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/DEVELOPMENT.md)

### Life Bot

Main product flow:

- capture tasks, reminders, follow-ups, and important dates
- parse natural language with AI first
- support multi-item extraction from one message
- fall back to pending rewrite mode when parsing is unsafe
- sync dated items to Google Calendar
- send Telegram reminders through the reminder tick endpoint

Docs:

- Product: [src/bot_platform/bots/life/README.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/README.md)
- Setup: [src/bot_platform/bots/life/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)
- Development: [src/bot_platform/bots/life/DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/DEVELOPMENT.md)

## Global Docs

- Setup: [docs/setup.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup.md)
- Development: [docs/development.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/development.md)
- Deployment: [docs/deployment.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/deployment.md)

## Quick Start

Install dependencies:

```bash
make install
```

Run local dev webhook server:

```bash
make local-dev
```

Expose it publicly:

```bash
make ngrok-dev
```

Set the finance webhook:

```bash
make webhook-set-dev
```

Set the life webhook:

```bash
make BOT=2 webhook-set-dev
```

## Runtime Notes

- `.env.dev` is for local development
- `.env` is for production-like runtime
- the FastAPI app currently serves both `/api/telegram_webhook` and `/api/life_telegram_webhook`
- `BOT=1` selects finance in Makefile webhook targets
- `BOT=2` selects life

## Shared Environment

Core environment values used across the platform:

- `DATABASE_URL`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PRIMARY_AI_PROVIDER`
- `GEMINI_API_KEY` and/or `OPENROUTER_API_KEY`
- `DEFAULT_TIMEZONE`

Bot-specific tokens:

- `TELEGRAM_BOT_TOKEN`
- `LIFE_TELEGRAM_BOT_TOKEN`

See [.env.example](/home/fairuz/Documents/learn/bot-finance-telegram/.env.example) for the current shape.
