# Life Bot Setup

## Required

- `LIFE_TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- one AI provider for AI-first parsing

Recommended:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_SHARE_HELP_EMAILS` for setup notes only
- `LIFE_GOOGLE_CALENDAR_ID`
- `LIFE_REMINDER_TICK_TOKEN`

## AI

The life bot is AI-first. It uses AI to:

- classify item type
- extract one or more items from one message
- recover from natural rewrite replies
- transcribe voice notes

If AI providers are not configured, the bot falls back to the local deterministic parser for simple single-item inputs.

## Google Calendar

To enable calendar sync:

1. Enable `Google Calendar API`
2. Create or choose a secondary calendar
3. Share it with the service account email
4. Give `Make changes to events`
5. Put the calendar ID into `LIFE_GOOGLE_CALENDAR_ID`

Do not use `primary` with a service account.

`GOOGLE_SHARE_HELP_EMAILS` is optional and informational only. It does not change authentication. The bot still authenticates as the service account from `GOOGLE_SERVICE_ACCOUNT_JSON`.

## Telegram Reminder Tick

Life bot Telegram reminders are sent by:

- `/api/life_reminder_tick`

This repo includes a GitHub Actions scheduler for that. Set these GitHub secrets:

- `LIFE_TICK_URL`
- `LIFE_REMINDER_TICK_TOKEN`

## Local Webhook

Life webhook endpoint:

- `/api/life_telegram_webhook`

Set it with:

```bash
make BOT=2 webhook-set-dev
```
