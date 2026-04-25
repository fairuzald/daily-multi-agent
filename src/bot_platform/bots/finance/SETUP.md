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

Recommended:

- `PRIMARY_AI_PROVIDER`
- `OPENROUTER_MODELS_TEXT`
- `OPENROUTER_MODELS_VISION`
- `OPENROUTER_MODELS_AUDIO`
- `DEFAULT_TIMEZONE`
- `LOW_CONFIDENCE_THRESHOLD`

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
4. Optionally add payment methods and categories with `/add_payment_method` and `/add_categories`
5. Save a test transaction

## Runtime Notes

- finance webhook endpoint: `/api/telegram_webhook`
- the finance bot now uses one unified extraction prompt for live text, voice, and image understanding
- reply-based finance follow-ups can append a new row while inheriting context from the replied transaction
- natural language is the default path; commands are mainly shortcuts and admin/setup helpers

## Local Webhook

Set it with:

```bash
make webhook-set-dev
```
