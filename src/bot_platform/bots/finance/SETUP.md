# Finance Bot Setup

## Required

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- one AI provider

If Gemini is primary:

- `GEMINI_API_KEY`

If OpenRouter is primary or fallback:

- `OPENROUTER_API_KEY`

## Google Sheets

The finance bot needs a Google Sheet shared with the service account as `Editor`.

Expected tabs:

- `Transactions`
- `Categories`
- `Summary`

The bot can repair headers and create missing tabs during setup.

## First-Time Flow

1. Send `/start`
2. Share the sheet with the service account email
3. Send the sheet link to the bot
4. Save a test transaction

## Local Webhook

Finance webhook endpoint:

- `/api/telegram_webhook`

Set it with:

```bash
make webhook-set-dev
```
