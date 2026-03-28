# Setup

This repo hosts two private Telegram bots on one platform runtime:

- `Finance Bot`
- `Life Bot`

Use this document for shared setup. Use the bot-local setup docs for product-specific steps.

## Shared Requirements

- Telegram bot token for each bot you want to run
- Postgres database reachable from the runtime
- at least one AI provider
- Google service account JSON if you use Google integrations

Core env:

- `DATABASE_URL`
- `PRIMARY_AI_PROVIDER`
- `GEMINI_API_KEY` and/or `OPENROUTER_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_SHARE_HELP_EMAILS` optional, informational only
- `DEFAULT_TIMEZONE`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_WEBHOOK_MAX_REQUESTS_PER_IP`
- `RATE_LIMIT_REMINDER_MAX_REQUESTS_PER_IP`

Bot tokens:

- `TELEGRAM_BOT_TOKEN`
- `LIFE_TELEGRAM_BOT_TOKEN`

## Environment Files

- `.env.dev` for local development
- `.env` for production-like runtime

The app loads `.env` by default. Make targets and local workflows explicitly load `.env.dev` where needed.

## Google Service Account

You need a Google service account when the bot uses:

- Google Sheets for the finance bot
- Google Calendar for the life bot

Setup:

1. Create or pick a Google Cloud project.
2. Enable the APIs you need:
   - `Google Sheets API`
   - `Google Calendar API`
3. Create a service account.
4. Create a JSON key.
5. Put the raw JSON into `GOOGLE_SERVICE_ACCOUNT_JSON`.

The service account email is the `client_email` inside that JSON.
If you set `GOOGLE_SHARE_HELP_EMAILS`, treat it as setup documentation only. It does not change which identity the bot uses. Google access still comes from `GOOGLE_SERVICE_ACCOUNT_JSON`.

## Finance Bot Setup

You also need:

- a Google Sheet shared with the service account as `Editor`
- `GOOGLE_SHEET_ID` or the `/start` flow to connect a sheet

Finance bot docs:

- [src/bot_platform/bots/finance/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/SETUP.md)

## Life Bot Setup

You also need:

- `LIFE_GOOGLE_CALENDAR_ID` if you want calendar sync
- `LIFE_REMINDER_TICK_TOKEN` if you want Telegram reminders

Important:

- do not use `primary` for service-account calendar writes
- create or choose a secondary calendar
- share that calendar with the service account using `Make changes to events`
- copy the real calendar ID from `Integrate calendar`

Life bot docs:

- [src/bot_platform/bots/life/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)

## Reminder Tick Setup

Life bot Telegram reminders are delivered by hitting:

- `/api/life_reminder_tick`

This repo includes a GitHub Actions workflow for that:

- `.github/workflows/life-reminder-tick.yml`

Secrets expected by the workflow:

- `LIFE_TICK_URL`
- `LIFE_REMINDER_TICK_TOKEN`

The workflow runs every 5 minutes.

## Reference

- Global development: [docs/development.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/development.md)
- Global deployment: [docs/deployment.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/deployment.md)
- Example env: [.env.example](/home/fairuz/Documents/learn/bot-finance-telegram/.env.example)
