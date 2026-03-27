# Bot Platform Finance Bot

Personal finance Telegram bot built on top of a reusable `bot_platform` package. It logs Indonesian transactions into Google Sheets, persists bot state in Postgres, and supports deterministic date handling, safer review flow, natural edit/delete/read commands, budgets, category learning, and month-over-month reporting.

## Features

- Log expenses, income, and transfers from Telegram chat
- Parse Indonesian finance language with Gemini only where deterministic logic is not enough
- Store structured records in Google Sheets
- Generate daily, weekly, monthly, and month-over-month summaries
- Bootstrap the required sheet tabs and headers
- Track daily spending across GoPay, BCA, BRI, DANA, and ShopeePay
- Lock the bot to one Telegram owner account
- Configure the active Google Sheet from chat by sending the sheet link
- Resolve common date expressions like `today`, `kemarin`, and `2 hari lalu` in code
- Queue ambiguous transactions for review instead of auto-saving them
- Support natural commands for delete, edit, read, and budget workflows
- Learn merchant/category mappings from confirmed corrections
- Run locally or in Docker Compose through the same FastAPI webhook flow

## Project Layout

- `api/telegram_webhook.py`: FastAPI webhook entrypoint
- `src/bot_platform/shared/bootstrap/factory.py`: dependency wiring and Telegram application assembly
- `src/bot_platform/shared/config/settings.py`: environment loading and typed settings
- `src/bot_platform/shared/persistence/json_store.py`: shared Postgres-backed key/value persistence
- `src/bot_platform/bots/finance/interfaces/telegram/controller.py`: Telegram controller and transport-level error handling
- `src/bot_platform/bots/finance/application/finance_bot_service.py`: finance bot workflows
- `src/bot_platform/bots/finance/domain/date_parser.py`: deterministic date handling
- `src/bot_platform/bots/finance/domain/command_parser.py`: deterministic command parsing
- `src/bot_platform/bots/finance/infrastructure/gemini_gateway.py`: Gemini integration
- `src/bot_platform/bots/finance/infrastructure/sheets_gateway.py`: Google Sheets integration
- `src/bot_platform/bots/finance/infrastructure/state_store.py`: persistent bot state
- `src/bot_platform/bots/finance/infrastructure/repositories.py`: budgets and learned mappings

## Setup

1. Install Poetry.
2. Install dependencies:

```bash
poetry install
```

3. Copy `.env.example` into `.env` and fill the values.
   The app and helper scripts load `.env` automatically from the project root, so you do not need to `source .env` first.

Google credentials must be provided as raw JSON in:

- `GOOGLE_SERVICE_ACCOUNT_JSON`

The bot stores its persistent owner/sheet setup in Postgres, configured by:

- `DATABASE_URL`

Optional env vars:

- `DEFAULT_CURRENCY`
- `DEFAULT_TIMEZONE`
- `LOW_CONFIDENCE_THRESHOLD`

## Sheet Initialization

The main bot now handles sheet initialization from chat after you send a Google Sheets link. It checks the required tabs and headers and fixes them if needed.

Required tabs:

- `Transactions`
- `Categories`
- `Summary`

## Run Locally

```bash
poetry run uvicorn api.telegram_webhook:app --reload --port 3000
```

This is the same webhook procedure used for production. Expose port `3000` with `ngrok` when you want Telegram to hit your local machine.

## Run With Docker Compose

```bash
docker compose up --build
```

The compose setup mounts `./data` into the container so the owner Telegram ID and active sheet selection survive restarts.
The compose setup runs a Postgres container and persists bot state in the `postgres_data` Docker volume so owner and active sheet survive restarts.

## Run Docker Compose In Dev Mode

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

This runs the same FastAPI webhook app with `uvicorn --reload` and bind-mounts the project so code changes trigger reload.

## Run Tests

```bash
poetry run env PYTHONPATH=src python -m pytest -q
```

## Usage Examples

- `/start`
- `/help`
- `/status`
- `/whoami`
- `/set_sheet`
- `/today`
- `/week`
- `beli kopi 25 ribu pakai bca`
- `makan siang 45000 kemarin pakai gopay`
- `gaji masuk 8 juta`
- `transfer 500 ribu dari BCA ke GoPay`
- `/month`
- `/delete_last`
- `/delete_reply`
- `/edit_last 30000 GoPay`
- `/edit_reply 30000 GoPay`
- `/read Food week`
- `/budget_set monthly category 500000 Food`
- `/budget_show monthly`
- `/compare_month`
- `delete last`
- `edit last 30000 pakai gopay`
- `show food this week`
- `set monthly food budget 500000`
- `show budget this month`
- `compare month`

## First-Chat Setup Flow

1. Start the bot with `/start`
2. The first Telegram user to do this becomes the owner
3. The bot asks for a Google Sheets link
4. Share that sheet with the service account email as `Editor`
5. Send the full Google Sheets link in chat
6. The bot extracts the sheet ID, verifies `Transactions`, `Categories`, and `Summary`, repairs headers if needed, seeds default categories when the categories tab is empty, and starts using that sheet

## Recap Commands

- `/today` uses today by default, or accepts `/today YYYY-MM-DD`
- `/week` uses the current week by default, or accepts `/week YYYY-MM-DD` or `/week YYYY-Www`
- `/month` uses the current month by default, or accepts `/month YYYY-MM` or `/month MM-YYYY`
- `/moth` is accepted as an alias for `/month`

## Strict Action Commands

- `/delete_last`
- `/delete_reply`
- `/edit_last <amount> [payment_method]`
- `/edit_reply <amount> [payment_method]`
- `/read <category> <today|week|month>`
- `/budget_set <weekly|monthly> <global|category> <amount> [category]`
- `/budget_show <weekly|monthly>`
- `/compare_month`

## Current Limitations

- The summary sheet is rebuilt from backend-generated rows rather than spreadsheet formulas.
- Public-edit Google Sheets links alone are not enough for reliable API writes; in practice you should still share the sheet with the service account as `Editor`.
- Google Sheets is the source of record for your transaction history.

## Webhook Deployment

The bot now uses one procedure everywhere: Telegram webhook -> FastAPI app -> Telegram controller -> finance application service.

### Vercel

Deploy the repo as an `Other` project. The Vercel entrypoint is the FastAPI app in:

- `api/telegram_webhook.py`

Required production env vars:

- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `DATABASE_URL`
- `LOW_CONFIDENCE_THRESHOLD`
- `DEFAULT_CURRENCY`
- `DEFAULT_TIMEZONE`

Important:

- `DATABASE_URL` must point to a hosted Postgres database reachable from Vercel
- the Docker Compose Postgres is only for local development

### Local Webhook Testing

Run the webhook app locally with FastAPI:

```bash
poetry run uvicorn api.telegram_webhook:app --reload --port 3000
```

Then expose it with `ngrok`:

```bash
ngrok http 3000
```

Your Telegram webhook URL should be:

```text
https://<your-ngrok-domain>/api/telegram_webhook
```

### Telegram Webhook Setup

After the Vercel deployment is live, register the Telegram webhook:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<your-vercel-domain>/api/telegram_webhook"
```

To inspect the current webhook:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

If you need to replace an old webhook URL, remove it first:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/deleteWebhook"
```

## Transactions Tab Layout

The bot writes the `Transactions` tab with this human-friendly column order:

- `Transaction ID`
- `Transaction Date`
- `Type`
- `Amount`
- `Subcategory`
- `Description`
- `Category`
- `Payment Method`
- `Destination Account / Wallet`
- `Merchant / Source`
- `Input Mode`
- `Raw Input`
- `AI Confidence`
- `Status`
