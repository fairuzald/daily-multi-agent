# Deployment

This guide covers production-oriented deployment for the finance bot.

## Runtime Shape

The production runtime is:

- Telegram webhook
- FastAPI app
- finance bot service
- external Postgres database
- Google Sheets API
- Gemini and/or OpenRouter

The bot should not depend on a Docker-managed local Postgres service in production.

## Supported Runtime Shapes

### Docker Production

- `make docker-prod`
- uses `.env`
- runs only the bot container
- expects external Postgres through `DATABASE_URL`

### Vercel

- uses `api/telegram_webhook.py`
- expects production env vars configured in the platform
- still depends on external Postgres and Google Sheets APIs

## Production Environment File

Use `.env` for production-like deployments.

Key variables:

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PRIMARY_AI_PROVIDER`
- `GEMINI_API_KEY` and/or `OPENROUTER_API_KEY`

## Database

`DATABASE_URL` must point to a hosted or otherwise externally reachable Postgres instance.

The bot stores:

- owner Telegram ID
- active sheet selection
- reply context
- pending confirmation state
- learned mappings
- budgets

## Docker

Production Docker should run only the bot app container and use the external database configured in `.env`.

It should not:

- start a local Postgres dependency
- override `DATABASE_URL` to point at a Compose-managed database

Useful targets:

```bash
make docker-prod
make docker-logs
make docker-down
make webhook-set-prod
make webhook-info-prod
make webhook-delete-prod
```

Operational expectation:

- `docker-compose.yml` no longer provisions Postgres
- `DATABASE_URL` is never overridden to a Compose-local database
- the same production env file drives both Docker and other hosted runtimes
- only `docker-compose.dev.yml` provisions a local Postgres service, and only for development
- dev-only service config lives under `docker/postgres` and `docker/dozzle`

## Vercel

If deployed to Vercel, the entrypoint is:

- `api/telegram_webhook.py`

Requirements:

- production environment variables configured in Vercel
- external Postgres database reachable from Vercel
- valid Telegram webhook URL

## Telegram Webhook Setup

If `WEBHOOK_URL` is set in `.env`, you can register the production webhook with:

```bash
make webhook-set-prod
```

Useful production webhook helpers:

- `make webhook-info-prod`
- `make webhook-delete-prod`

Set the webhook:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<your-domain>/api/telegram_webhook"
```

Inspect the webhook:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

Delete the webhook:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/deleteWebhook"
```

## Operational Notes

- if Gemini is primary and exhausted, the bot can fall back to OpenRouter
- if OpenRouter is configured with model pools, it will try the next model when the current one fails with retryable provider/model errors
- Google Sheet header repair is intended to be non-destructive
- `.env.dev` is for development only; production-like runtimes should use `.env`

## Recommended Checks After Deployment

- `/start` works for the owner
- sheet connection succeeds
- a test expense saves correctly
- a voice note can be transcribed
- a screenshot can be parsed
- `/today`, `/month`, and `/compare_month` work
