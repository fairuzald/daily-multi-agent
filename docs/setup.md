# Setup

This guide covers the minimum setup required to run the finance bot against a real Telegram bot, Google Sheet, and external Postgres database.

## What You Need

- a Telegram bot token from BotFather
- a Google Cloud service account with Google Sheets access
- a Google Sheet shared with that service account as `Editor`
- a Postgres database reachable from wherever the bot runs
- at least one AI provider:
  - Gemini
  - OpenRouter

## Environment Files

The project uses two main environment files:

- `.env` for production-like runtime
- `.env.dev` for local development

The app itself loads `.env` by default. The Make targets and Docker development workflow explicitly use `.env.dev` for local work.

## Runtime Modes

### Local Development

- use `.env.dev`
- intended for `make local-dev`
- can point to a local or hosted Postgres database

### Production-Like Local Run

- use `.env`
- intended for `make local-prod`

### Docker Development

- uses `.env.dev`
- intended for `make docker-dev`
- includes Dozzle for container log viewing
- provisions its own Postgres container
- overrides the bot container `DATABASE_URL` to point at that dev Postgres service

### Docker Production

- uses `.env`
- intended for `make docker-prod`
- runs only the bot container
- does not provision Postgres

## Required Environment Variables

### Telegram

- `TELEGRAM_BOT_TOKEN`

### Storage

- `DATABASE_URL`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

`DATABASE_URL` must always point to a reachable external database from the runtime that uses it.

Important for Docker:

- if the bot runs inside Docker, `localhost` usually means the container itself
- if your DB runs on the host machine, use a host reachable from the container such as `host.docker.internal` where supported
- if your DB is hosted remotely, use its hosted connection string directly
- `docker-compose.dev.yml` is the exception: it injects its own container-local Postgres URL for the bot automatically

### AI

- `PRIMARY_AI_PROVIDER`
  - allowed values: `gemini`, `openrouter`

For Gemini primary or fallback:

- `GEMINI_API_KEY`

For OpenRouter primary or fallback:

- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`

## OpenRouter Model Pools

OpenRouter supports comma-separated model pools per capability:

- `OPENROUTER_MODELS_TEXT`
- `OPENROUTER_MODELS_VISION`
- `OPENROUTER_MODELS_AUDIO`

Example:

```env
OPENROUTER_MODELS_TEXT=openrouter/free,google/gemini-2.5-flash-preview
OPENROUTER_MODELS_VISION=openrouter/free,google/gemini-2.5-flash-preview
OPENROUTER_MODELS_AUDIO=openai/whisper-large-v3,openai/gpt-4o-mini-transcribe
```

Behavior:

- the bot tries the configured models in order
- if one model fails with a retryable provider/model error, it uses the next one
- after a success, the next request rotates forward naturally

Use only the `OPENROUTER_MODELS_*` variables. The older single-model variables are no longer supported.

Do not use `openrouter/free` for audio.

## Optional Bot Defaults

- `DEFAULT_CURRENCY`
- `DEFAULT_TIMEZONE`
- `LOW_CONFIDENCE_THRESHOLD`
- `AI_FALLBACK_COOLDOWN_SECONDS`

## Dev Docker Postgres Config

The dev Docker Postgres service reads its own env file from:

- `docker/postgres/.env`

Reference values live in:

- `docker/postgres/.env.example`

Supported keys there:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`

## Google Sheet Setup

The bot expects these tabs:

- `Transactions`
- `Categories`
- `Summary`

The bot can create or repair these headers automatically when the sheet is connected.

Important:

- the sheet must be shared with the service account as `Editor`
- the bot now repairs headers in place and should not clear existing rows during normal schema checks

## First Telegram Setup Flow

1. Send `/start`
2. The first Telegram user becomes the owner
3. The bot asks for a Google Sheets link
4. Share the sheet with the service account email as `Editor`
5. Send the full Google Sheets link in chat

## Reference

See [.env.example](/home/fairuz/Documents/learn/bot-finance-telegram/.env.example) for the current config shape.

See [docs/development.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/development.md) for local commands and [docs/deployment.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/deployment.md) for production runtime guidance.
