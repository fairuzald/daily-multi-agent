# Bot Platform

Private Telegram bot platform for one-owner workflows.

This repo currently contains two bots:

- `Finance Bot` for daily money tracking into Google Sheets
- `Life Bot` for tasks, reminders, follow-ups, important dates, and Google Calendar sync

Both bots share the same runtime foundations:

- FastAPI webhook endpoints
- Postgres-backed state and pending-context storage
- provider-routed AI with fallback
- owner-only access control

## Webhook Endpoints

- Finance: `/api/telegram_webhook`
- Life: `/api/life_telegram_webhook`
- Life reminder tick: `/api/life_reminder_tick`

## Finance Bot

Current behavior:

- natural-language-first for text, voice, screenshots, and reply-based follow-ups
- one unified AI extractor prompt for live message understanding
- clarification-first when the bot is unsure
- replying to a saved finance message can append a new transaction with inherited context, not just edit the old one
- reply-based edit/delete plus summaries, budgets, and comparisons
- Google Sheets persistence

Main docs:

- Product: [src/bot_platform/bots/finance/README.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/README.md)
- Setup: [src/bot_platform/bots/finance/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/SETUP.md)
- Development: [src/bot_platform/bots/finance/DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/DEVELOPMENT.md)

## Life Bot

Current behavior:

- AI-first natural-language capture for tasks, reminders, follow-ups, and important dates
- one unified AI extractor prompt for new messages and rewrites
- reply-based actions like done, view, edit, cancel, and snooze
- recurring reminders with `until` date support
- Google Calendar sync for dated items
- Telegram reminder delivery through the reminder tick endpoint

Main docs:

- Product: [src/bot_platform/bots/life/README.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/README.md)
- Setup: [src/bot_platform/bots/life/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)
- Development: [src/bot_platform/bots/life/DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/DEVELOPMENT.md)

## Setup

- Start here: [docs/setup.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup.md)
- Local onboarding: [docs/setup-local.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup-local.md)
- Production onboarding: [docs/setup-production.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup-production.md)

## Architecture

- Pipeline overview: [docs/bot-pipelines.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/bot-pipelines.md)
- Diagram asset: [docs/assets/bot-pipelines.svg](/home/fairuz/Documents/learn/bot-finance-telegram/docs/assets/bot-pipelines.svg)

## Quick Start

Install dependencies:

```bash
make install
```

Run local dev webhook server:

```bash
make local-dev
```

Expose it publicly:

```bash
make ngrok-dev
```

Set the finance webhook:

```bash
make webhook-set-dev
```

Set the life webhook:

```bash
make BOT=2 webhook-set-dev
```

For a full clone-to-running guide, use [docs/setup-local.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup-local.md).
For deployment and production webhooks, use [docs/setup-production.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup-production.md).

## Runtime Notes

- `.env.dev` is for local development
- `.env` is for production-like runtime
- `BOT=1` selects finance in Makefile webhook targets
- `BOT=2` selects life
- see [.env.example](/home/fairuz/Documents/learn/bot-finance-telegram/.env.example) for current environment variables
