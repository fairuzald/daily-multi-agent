# Local Setup

Use this guide when you have just cloned the repo and want to run the bots locally.

## What You Will End Up With

After this guide you should have:

- dependencies installed
- a local `.env.dev`
- the app running on your machine
- a public ngrok URL
- one or both Telegram bots pointing at your local webhook

## Prerequisites

Install these first:

- Python 3.11+
- Poetry
- Docker and Docker Compose
- ngrok
- Telegram app access for BotFather setup

Clone the repo and enter it:

```bash
git clone <your-repo-url>
cd bot-finance-telegram
```

## 1. Create Your Local Env File

Start from the example env:

```bash
cp .env.example .env.dev
```

Fill in the values you actually plan to use in local development.

Minimum shared values:

- `DATABASE_URL`
- `PRIMARY_AI_PROVIDER`
- AI credentials for that provider
- `DEFAULT_TIMEZONE`

If you are running the finance bot:

- `TELEGRAM_BOT_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

If you are running the life bot:

- `LIFE_TELEGRAM_BOT_TOKEN`

Optional for life bot local testing:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `LIFE_GOOGLE_CALENDAR_ID`
- `LIFE_REMINDER_TICK_TOKEN`

Reference:

- env template: [.env.example](/home/fairuz/Documents/learn/bot-finance-telegram/.env.example)
- shared setup notes: [docs/setup.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup.md)

## 2. Create Your Telegram Bots In BotFather

Bot creation still has to be done manually in Telegram with `@BotFather`.

Recommended pattern if you want both bots:

- create the finance bot first
- create the life bot second
- copy each token immediately into `.env.dev`

Suggested BotFather checklist for each bot:

1. Run `/newbot`
2. Enter the display name
3. Enter a unique username ending in `bot`
4. Copy the token
5. Put the token into `.env.dev`
6. Optionally run `/setuserpic`
7. Optionally run `/setdescription`
8. Optionally run `/setabouttext`
9. Optionally run `/setcommands`

Map the tokens like this:

- finance bot token -> `TELEGRAM_BOT_TOKEN`
- life bot token -> `LIFE_TELEGRAM_BOT_TOKEN`

Keep BotFather work minimal at this stage. You only need valid tokens to continue.

## 3. Install Dependencies

Install Python dependencies:

```bash
make install
```

## 4. Start Local Infrastructure

If you are using the local Docker workflow:

```bash
make docker-dev
```

If you only want to run the app process locally and your database already exists elsewhere, start just the app:

```bash
make local-dev
```

## 5. Expose Your Local App Publicly

Telegram webhooks need a public HTTPS URL.

Start ngrok:

```bash
make ngrok-dev
```

Copy the HTTPS forwarding URL and set it in `.env.dev` as:

- `WEBHOOK_URL=https://your-ngrok-domain`

## 6. Register Telegram Webhooks

With the app running and `WEBHOOK_URL` set, register the bot webhook.

Finance bot:

```bash
make webhook-set-dev
```

Life bot:

```bash
make BOT=2 webhook-set-dev
```

Check webhook status:

Finance bot:

```bash
make webhook-info-dev
```

Life bot:

```bash
make BOT=2 webhook-info-dev
```

If you need to clear a webhook:

Finance bot:

```bash
make webhook-delete-dev
```

Life bot:

```bash
make BOT=2 webhook-delete-dev
```

## 7. First Run Checks In Telegram

Finance bot first-use flow:

1. Send `/start`
2. Share the Google Sheet with the service account email
3. Send the sheet link to the bot
4. Save a test transaction

Life bot first-use flow:

1. Send `/start`
2. Run `/whoami`
3. Save a test reminder or task

Bot-specific references:

- finance setup: [src/bot_platform/bots/finance/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/SETUP.md)
- life setup: [src/bot_platform/bots/life/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)

## 8. Common Local Verification

Use these checks before debugging the bot behavior:

- confirm `.env.dev` has the right token in the right variable
- confirm `WEBHOOK_URL` matches the active ngrok URL
- confirm the app is running on port `3000`
- confirm `make webhook-info-dev` or `make BOT=2 webhook-info-dev` returns the expected webhook URL
- confirm you are messaging the same bot whose token you registered

## 9. Useful Local Commands

```bash
make test
make docker-logs-dev
make docker-down
```

Bot-specific development references:

- finance development: [src/bot_platform/bots/finance/DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/DEVELOPMENT.md)
- life development: [src/bot_platform/bots/life/DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/DEVELOPMENT.md)

## 10. Next Step

If local development is working and you want to deploy the bots publicly, continue with [docs/setup-production.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup-production.md).
