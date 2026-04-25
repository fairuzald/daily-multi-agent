# Bot Platform

Private Telegram bot platform for one-owner workflows. The repo currently contains two bots:

- `Finance Bot` for expense tracking into Google Sheets
- `Life Bot` for tasks, reminders, follow-ups, important dates, and Google Calendar sync

Both bots share the same runtime patterns:

- Telegram webhook via FastAPI
- Postgres-backed state store
- provider-routed AI
- owner-only access control

## Bots

### Finance Bot

Main product flow:

- parse Indonesian text, voice notes, and screenshots
- store structured transactions in Google Sheets
- support reply-based review, correction, deletion, budgets, and summaries

Docs:

- Product: [src/bot_platform/bots/finance/README.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/README.md)flowchart TD
  U[Telegram User]

  subgraph Finance Bot
  F1[Telegram Controller]
  F2[Voice Transcription]
  F3[Message Entry Service]
  F4[Pending or Reply State Check]
  F5[AI Intent Interpreter]
  F6{Intent Type}
  F7[Command Service]
  F8[Multi Transaction Detection]
  F9[Transaction Parser]
  F10[Image Parser]
  F11[Deterministic Enrichment]
  F12[Policy Validation]
  F13{Clarify?}
  F14[Pending State Store]
  F15[Human Clarification]
  F16[Persistence]
  F17[Google Sheets]
  F18[Human Confirmation or Summary]
  end

  subgraph Life Bot
  L1[Telegram Controller]
  L2[Voice Transcription]
  L3[Message Service]
  L4[Pending or Reply State Check]
  L5[Inline Actions]
  L6[Life Parser]
  L7{Confirm or Rewrite?}
  L8[Pending State Store]
  L9[Human Clarification]
  L10[Item Service]
  L11[Repository]
  L12[Google Calendar Sync]
  L13[Human Result]
  end

  U --> F1
  F1 -->|voice| F2
  F1 -->|text| F3
  F2 --> F3
  F3 --> F4
  F4 --> F5
  F5 --> F6
  F6 -->|action| F7
  F6 -->|transaction| F8
  F6 -->|clarify| F15
  F8 -->|grouped| F11
  F8 -->|single| F9
  F1 -->|image| F10
  F9 --> F11
  F10 --> F11
  F11 --> F12
  F12 --> F13
  F13 -->|yes| F14
  F14 --> F15
  F13 -->|no| F16
  F16 --> F17
  F16 --> F18
  F7 --> F18

  U --> L1
  L1 -->|voice| L2
  L1 -->|text| L3
  L2 --> L3
  L3 --> L4
  L4 --> L5
  L5 -->|handled| L13
  L5 -->|not handled| L6
  L6 --> L7
  L7 -->|yes| L8
  L8 --> L9
  L7 -->|no| L10
  L10 --> L11
  L10 --> L12
  L10 --> L13

- Setup: [src/bot_platform/bots/finance/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/SETUP.md)
- Development: [src/bot_platform/bots/finance/DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/DEVELOPMENT.md)

### Life Bot

Main product flow:

- capture tasks, reminders, follow-ups, and important dates
- parse natural language with AI first
- support multi-item extraction from one message
- fall back to pending rewrite mode when parsing is unsafe
- sync dated items to Google Calendar
- send Telegram reminders through the reminder tick endpoint

Docs:

- Product: [src/bot_platform/bots/life/README.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/README.md)
- Setup: [src/bot_platform/bots/life/SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)
- Development: [src/bot_platform/bots/life/DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/DEVELOPMENT.md)

## Global Docs

- Setup: [docs/setup.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup.md)
- Development: [docs/development.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/development.md)
- Deployment: [docs/deployment.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/deployment.md)

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

## Runtime Notes

- `.env.dev` is for local development
- `.env` is for production-like runtime
- the FastAPI app currently serves both `/api/telegram_webhook` and `/api/life_telegram_webhook`
- `BOT=1` selects finance in Makefile webhook targets
- `BOT=2` selects life

## Shared Environment

Core environment values used across the platform:

- `DATABASE_URL`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `PRIMARY_AI_PROVIDER`
- `GEMINI_API_KEY` and/or `OPENROUTER_API_KEY`
- `DEFAULT_TIMEZONE`

Bot-specific tokens:

- `TELEGRAM_BOT_TOKEN`
- `LIFE_TELEGRAM_BOT_TOKEN`

See [.env.example](/home/fairuz/Documents/learn/bot-finance-telegram/.env.example) for the current shape.
