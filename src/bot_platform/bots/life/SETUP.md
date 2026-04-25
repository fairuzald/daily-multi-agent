# Life Bot Setup

## Required

- `LIFE_TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- one AI provider for AI-first parsing

Recommended:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `LIFE_GOOGLE_CALENDAR_ID`
- `LIFE_REMINDER_TICK_TOKEN`

## AI

The life bot is AI-first. It uses AI to:

- extract one or more items from one message
- handle natural rewrite replies through the same unified extraction path
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

## Telegram Reminder Tick

Life bot Telegram reminders are sent by:

- `/api/life_reminder_tick`

This repo includes a GitHub Actions scheduler for that. Set these GitHub secrets:

- `LIFE_TICK_URL`
- `LIFE_REMINDER_TICK_TOKEN`

Reminder notes:

- recurring reminders can include an `until` date
- the reminder tick should run repeatedly, for example every 5 minutes

## Local Webhook
## First Use

1. Send `/start` from the owner account in that environment
2. Then test `/whoami`
3. If using calendar sync, share the calendar with the service account
4. Then start saving reminders and tasks

Life webhook endpoint:

- `/api/life_telegram_webhook`

Set it with:

```bash
make BOT=2 webhook-set-dev
```
