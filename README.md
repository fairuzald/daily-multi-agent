# Telegram Finance Bot

Personal finance Telegram bot that logs Indonesian transactions into Google Sheets and generates monthly summaries. The bot is locked to one Telegram owner user ID after first setup and the active Google Sheet is configured from chat by sending a spreadsheet link.

## Features

- Log expenses, income, and transfers from Telegram chat
- Parse Indonesian finance language with Gemini
- Store structured records in Google Sheets
- Generate monthly summary rows and improvement insights
- Bootstrap the required sheet tabs and headers
- Track daily spending across GoPay, BCA, BRI, DANA, and ShopeePay
- Lock the bot to one Telegram owner account
- Configure the active Google Sheet from chat by sending the sheet link
- Run locally with Poetry or in Docker Compose

## Project Layout

- `src/bot_finance_telegram/app.py`: Telegram entrypoint
- `src/bot_finance_telegram/handlers.py`: bot workflows
- `src/bot_finance_telegram/services/gemini_client.py`: Gemini integration
- `src/bot_finance_telegram/services/sheets_client.py`: Google Sheets integration
- `src/bot_finance_telegram/services/summary_service.py`: monthly summary logic

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

## Sheet Initialization

The main bot now handles sheet initialization from chat after you send a Google Sheets link. It checks the required tabs and headers and fixes them if needed.

Required tabs:

- `Transactions`
- `Categories`
- `Summary`

## Run The Bot

```bash
poetry run python -m bot_finance_telegram.app
```

## Run The Bot In Dev Mode

```bash
DEV_MODE=true poetry run python -m bot_finance_telegram.app
```

When `DEV_MODE=true`, the bot auto-reloads on changes in `src/`, `scripts/`, and `.env`.

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

This enables `DEV_MODE=true` for the bot container and bind-mounts the project so code changes trigger auto-reload.

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
- `beli kopi 25 ribu pakai bca`
- `gaji masuk 8 juta`
- `transfer 500 ribu dari BCA ke GoPay`
- `/month`

## First-Chat Setup Flow

1. Start the bot with `/start`
2. The first Telegram user to do this becomes the owner
3. The bot asks for a Google Sheets link
4. Share that sheet with the service account email as `Editor`
5. Send the full Google Sheets link in chat
6. The bot extracts the sheet ID, verifies `Transactions`, `Categories`, and `Summary`, repairs headers if needed, seeds default categories when the categories tab is empty, and starts using that sheet

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
- `Account / Wallet`
- `Destination Account / Wallet`
- `Merchant / Source`
- `Input Mode`
- `Raw Input`
- `AI Confidence`
- `Status`

## Current Limitations

- Telegram voice-note download and Gemini audio transcription wiring still needs deployment-specific setup.
- Transaction confirmation state is still in memory only; owner ID and active sheet selection are persisted.
- The summary sheet is rebuilt from backend-generated rows rather than spreadsheet formulas.
- Public-edit Google Sheets links alone are not enough for reliable API writes; in practice you should still share the sheet with the service account as `Editor`.
