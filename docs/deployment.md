# Deployment

This repo can be deployed as one FastAPI webhook app serving both bots.

## Runtime Shape

- FastAPI webhook app
- Telegram webhook endpoints
- external Postgres
- AI provider credentials
- optional Google Sheets and Google Calendar integrations

## Endpoints

- `/api/telegram_webhook` for finance
- `/api/life_telegram_webhook` for life
- `/api/life_reminder_tick` for life Telegram reminders

## Environment

Production-like runtime uses `.env`.

Common values:

- `DATABASE_URL`
- `PRIMARY_AI_PROVIDER`
- `GEMINI_API_KEY` and/or `OPENROUTER_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_WEBHOOK_MAX_REQUESTS_PER_IP`
- `RATE_LIMIT_REMINDER_MAX_REQUESTS_PER_IP`

Finance:

- `TELEGRAM_BOT_TOKEN`

Life:

- `LIFE_TELEGRAM_BOT_TOKEN`
- `LIFE_GOOGLE_CALENDAR_ID`
- `LIFE_REMINDER_TICK_TOKEN`

## Docker

Production Docker runs only the bot app container and expects external Postgres.

Useful targets:

```bash
make docker-prod
make docker-logs
make docker-down
```

## Vercel

If deployed to Vercel:

- use `api/telegram_webhook.py`
- provide all production env vars
- keep Postgres external
- register both Telegram webhooks separately

## Webhook Registration

Finance:

```bash
make webhook-set-prod
```

Life:

```bash
make BOT=2 webhook-set-prod
```

## Life Reminder Scheduler

The life bot needs a scheduler for Telegram reminders. This repo ships a GitHub Actions workflow that hits the reminder tick every 5 minutes.

Workflow:

- `.github/workflows/life-reminder-tick.yml`

Secrets:

- `LIFE_TICK_URL_DEV`
- `LIFE_REMINDER_TICK_TOKEN_DEV`
- `LIFE_TICK_URL_MAIN`
- `LIFE_REMINDER_TICK_TOKEN_MAIN`

If you do not run that scheduler:

- life items still save
- Google Calendar sync still works
- Telegram reminders will not be pushed automatically

## HTTP Rate Limiting

The FastAPI entrypoints now apply per-IP fixed-window rate limits:

- finance webhook
- life webhook
- life reminder tick

The defaults are intended to be conservative protection, not hard anti-bot security:

- webhook endpoints: `120` requests per IP per `60` seconds
- reminder tick: `12` requests per IP per `60` seconds

Tune them with env if your deployment shape needs different limits.

## Bot-Specific Deployment Notes

- Finance setup details: [src/bot_platform/bots/finance/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/SETUP.md)
- Life setup details: [src/bot_platform/bots/life/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)
