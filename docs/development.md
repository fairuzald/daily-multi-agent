# Development

This guide covers local development for the finance bot.

## Development Targets

The repo now provides a `Makefile` for the main workflows:

```bash
make install
make test
make local-dev
make local-prod
make ngrok-dev
make webhook-set-dev
make webhook-info-dev
make webhook-delete-dev
make docker-dev
make docker-logs-dev
make docker-down
```

## Install Dependencies

```bash
poetry install
```

## Local Environment

Use `.env.dev` for local development values. Keep `.env` for production-like runtime values.

Typical local requirements:

- Telegram bot token
- reachable external Postgres database
- Google service account JSON
- Gemini and/or OpenRouter credentials

## Run Locally

Run the FastAPI webhook app directly:

```bash
poetry run uvicorn api.telegram_webhook:app --reload --port 3000
```

Or use the Make targets:

```bash
make local-dev
make local-prod
```

Behavior:

- `make local-dev` loads `.env.dev` and runs `uvicorn` with `--reload`
- `make local-prod` loads `.env` and runs without reload

The Telegram bot still needs a public webhook target. For local testing, expose port `3000` with a tunnel such as `ngrok`.

Recommended local Telegram webhook flow:

```bash
make local-dev
make ngrok-dev
make webhook-set-dev
```

Useful webhook helpers:

- `make webhook-info-dev`
- `make webhook-delete-dev`

Set `WEBHOOK_URL` in `.env.dev` to your ngrok URL before running `make webhook-set-dev`.

## Run Tests

Full test suite:

```bash
poetry run python -m pytest -q
```

Targeted suite:

```bash
poetry run python -m pytest -q tests/test_ai_fallback.py tests/test_config_and_sheets.py
```

## Docker Development

Development Compose should be used for:

- bind-mounted source code
- autoreload
- log viewing with Dozzle
- `.env.dev`-based runtime

The development stack now includes:

- the bot container
- a dev Postgres container
- Dozzle on port `8080`

The service definitions live under the `docker/` folder:

- `docker/postgres/docker-compose.yml`
- `docker/dozzle/docker-compose.yml`

The top-level `docker-compose.yml` and `docker-compose.dev.yml` stay thin and environment-specific.

In Docker dev, the bot container does not use the `DATABASE_URL` value from `.env.dev`.
It is overridden to connect to the `postgres` service defined in `docker-compose.dev.yml`.
The Postgres container reads its own env file from `docker/postgres/.env`.

Useful targets:

```bash
make docker-dev
make docker-logs-dev
make docker-down
```

Important:

- for `make docker-dev`, adjust `docker/postgres/.env` if you want different dev DB credentials
- `POSTGRES_PORT` controls the host port published for the dev Postgres container
- for `make local-dev`, `DATABASE_URL` in `.env.dev` is still used directly

## Production-Like Docker From Dev Machine

If you want to test the production-like container shape locally:

```bash
make docker-prod
make docker-logs
```

This uses `.env`, runs only the bot container, and still expects an external database.

## What To Verify During Development

- sheet setup does not clear existing rows
- pending confirmations only work via explicit reply
- grouped multi-item transactions behave correctly
- OpenRouter model-pool failover behaves correctly for text, image, and audio

## Main Code Areas

- `api/telegram_webhook.py`
- `src/bot_platform/shared/bootstrap/factory.py`
- `src/bot_platform/shared/config/settings.py`
- `src/bot_platform/bots/finance/application/finance_bot_service.py`
- `src/bot_platform/bots/finance/interfaces/telegram/controller.py`
- `src/bot_platform/bots/finance/infrastructure/sheets_gateway.py`
- `src/bot_platform/bots/finance/infrastructure/openrouter_gateway.py`
