# Setup

Start here if you are cloning this repo for the first time.

This project hosts two private Telegram bots on one FastAPI runtime:

- `Finance Bot`
- `Life Bot`

Use the docs below in this order:

- Local onboarding: [docs/setup-local.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup-local.md)
- Production onboarding: [docs/setup-production.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup-production.md)

Use the bot-specific setup docs after the shared onboarding is done:

- Finance bot setup: [src/bot_platform/bots/finance/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/SETUP.md)
- Life bot setup: [src/bot_platform/bots/life/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)

## Shared Requirements

You will need:

- one Telegram bot token per bot you want to run
- a Postgres database
- at least one AI provider
- a Google service account JSON if you use Google Sheets or Google Calendar

Core environment variables:

- `DATABASE_URL`
- `PRIMARY_AI_PROVIDER`
- `GEMINI_API_KEY` and/or `OPENROUTER_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `DEFAULT_TIMEZONE`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_WEBHOOK_MAX_REQUESTS_PER_IP`
- `RATE_LIMIT_REMINDER_MAX_REQUESTS_PER_IP`

Bot token variables:

- `TELEGRAM_BOT_TOKEN`
- `LIFE_TELEGRAM_BOT_TOKEN`

## Environment Files

- `.env.dev` for local development
- `.env` for production-like runtime

Use [.env.example](/home/fairuz/Documents/learn/bot-finance-telegram/.env.example) as the starting point for both.

## Shared Runtime Endpoints

- finance webhook: `/api/telegram_webhook`
- life webhook: `/api/life_telegram_webhook`
- life reminder tick: `/api/life_reminder_tick`

## Related Docs

- Finance setup: [src/bot_platform/bots/finance/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/SETUP.md)
- Life setup: [src/bot_platform/bots/life/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)
