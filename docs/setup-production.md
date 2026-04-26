# Production Setup

Use this guide when you want to deploy the app with public webhooks.

## What You Will End Up With

After this guide you should have:

- a production `.env`
- the app deployed on a public HTTPS domain
- Telegram webhooks registered for one or both bots
- life reminder delivery configured if you use the life bot

## 1. Decide What You Are Deploying

This repo can serve both bots from one FastAPI app.

Shared endpoints:

- finance webhook: `/api/telegram_webhook`
- life webhook: `/api/life_telegram_webhook`
- life reminder tick: `/api/life_reminder_tick`

You can deploy:

- finance bot only
- life bot only
- both bots on the same app

## 2. Prepare Your Production Env File

Start from the example env:

```bash
cp .env.example .env
```

Fill in the shared production values:

- `DATABASE_URL`
- `PRIMARY_AI_PROVIDER`
- AI credentials
- `DEFAULT_TIMEZONE`
- rate-limit values

Add bot tokens as needed:

- `TELEGRAM_BOT_TOKEN` for finance
- `LIFE_TELEGRAM_BOT_TOKEN` for life

Add Google integration values if used:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `LIFE_GOOGLE_CALENDAR_ID`
- `LIFE_REMINDER_TICK_TOKEN`

Set your public base URL as:

- `WEBHOOK_URL=https://your-public-domain`

Reference:

- env template: [.env.example](/home/fairuz/Documents/learn/bot-finance-telegram/.env.example)

## 3. Create Or Reuse BotFather Bots

BotFather work is still manual and should be done before deployment.

For each bot:

1. Create it with `/newbot` if it does not exist yet
2. Copy the token into `.env`
3. Optionally set icon, description, about text, and commands
4. Keep the token private and rotate it if it was exposed

Token mapping:

- finance bot token -> `TELEGRAM_BOT_TOKEN`
- life bot token -> `LIFE_TELEGRAM_BOT_TOKEN`

## 4. Deploy The App

Production Docker targets:

```bash
make docker-prod
make docker-logs
```

If you use another platform such as Vercel, keep these assumptions the same:

- all required env vars are present
- Postgres is external
- the app is reachable on HTTPS
- the webhook endpoints keep the same paths

Platform notes:

- Docker production uses `make docker-prod`, `make docker-logs`, and `make docker-down`
- If you deploy on Vercel, keep the same env variables, use external Postgres, and register both Telegram webhooks separately

## 5. Register Production Webhooks

Once the deployment is live and `WEBHOOK_URL` points at the correct public domain:

Finance bot:

```bash
make webhook-set-prod
```

Life bot:

```bash
make BOT=2 webhook-set-prod
```

Check webhook status:

Finance bot:

```bash
make webhook-info-prod
```

Life bot:

```bash
make BOT=2 webhook-info-prod
```

If you need to clear a webhook:

Finance bot:

```bash
make webhook-delete-prod
```

Life bot:

```bash
make BOT=2 webhook-delete-prod
```

## 6. Complete Product-Specific Setup

Finance bot:

1. Send `/start`
2. Share the Google Sheet with the service account email
3. Send the sheet link to the bot
4. Save a test transaction

Life bot:

1. Send `/start`
2. Run `/whoami`
3. If using calendar sync, share the calendar with the service account
4. Save a test reminder

References:

- finance setup: [src/bot_platform/bots/finance/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/SETUP.md)
- life setup: [src/bot_platform/bots/life/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)

## 7. Configure Life Reminder Delivery

If you use the life bot and want Telegram reminders to be pushed automatically, configure the reminder tick scheduler.

This repo expects:

- endpoint: `/api/life_reminder_tick`
- secret: `LIFE_REMINDER_TICK_TOKEN`

The repo includes a GitHub Actions workflow that should call the tick every 5 minutes.

Required secrets:

- `LIFE_TICK_URL`
- `LIFE_REMINDER_TICK_TOKEN`

If you do not run the scheduler:

- life items still save
- calendar sync can still work
- Telegram reminders will not be delivered automatically

## 8. HTTP Rate Limiting

The webhook entrypoints apply per-IP fixed-window rate limits.

Defaults from env:

- webhook endpoints: `120` requests per IP per `60` seconds
- reminder tick: `12` requests per IP per `60` seconds

Tune them with:

- `RATE_LIMIT_WINDOW_SECONDS`
- `RATE_LIMIT_WEBHOOK_MAX_REQUESTS_PER_IP`
- `RATE_LIMIT_REMINDER_MAX_REQUESTS_PER_IP`

## 9. Production Verification Checklist

Before calling the deployment done, verify:

- the app is reachable over HTTPS
- the correct tokens are stored in `.env`
- `WEBHOOK_URL` is the real public base URL
- `make webhook-info-prod` returns the expected finance webhook URL
- `make BOT=2 webhook-info-prod` returns the expected life webhook URL
- `/start` works from your owner account
- finance bot can save a test transaction
- life bot can save a test reminder
- the reminder tick works if enabled

## 10. Rollback And Recovery Basics

If Telegram is still sending to an old endpoint, clear and re-register the webhook.

If a token was leaked:

1. rotate it in BotFather
2. update `.env`
3. redeploy
4. re-register the webhook

If deployment is healthy but the bot does not respond:

- verify the webhook URL path is correct for that bot
- verify the token belongs to the bot you are messaging
- inspect runtime logs with `make docker-logs`
