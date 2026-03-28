# Bot Platform Finance Bot

Personal finance Telegram bot for daily money tracking in Indonesian. It turns natural chat, voice notes, and payment screenshots into structured transactions stored in Google Sheets, while keeping review flows safe for ambiguous inputs.

The runtime model is now simple:

- local development uses `.env.dev`
- production-like runtime uses `.env`
- Docker Compose runs only the bot container
- Postgres must be external and reachable through `DATABASE_URL`

## What This Product Does

This bot is built for one owner-operated personal finance workflow:

- capture expenses, income, and transfers directly from Telegram
- save transactions into a connected Google Sheet
- keep a Postgres-backed memory for owner access, reply context, budgets, and learned mappings
- generate daily, weekly, monthly, and month-to-month summaries
- support safer review when an input is ambiguous instead of silently guessing

It is optimized for casual Indonesian finance messages like:

- `beli kopi 25000 pakai bca`
- `makan siang 45000 kemarin pakai gopay`
- `gaji masuk 8000000 ke bri`
- `transfer 500000 dari BCA ke GoPay`

## Main Capabilities

### 1. Transaction Capture

The bot can record:

- expenses
- income
- transfers between accounts or wallets

It accepts:

- natural text messages
- Indonesian voice notes
- receipt, payment, and transaction screenshots

### 2. Smart Parsing With Safer Review

The bot combines deterministic logic with AI parsing:

- common date phrases like `today`, `kemarin`, `2 hari lalu`, and exact dates are resolved in code
- learned merchant and category mappings are reused before asking AI again
- low-confidence or incomplete results can be kept in review instead of auto-saved
- grouped messages with multiple items can be split into multiple rows

Examples:

- `es teh 2000 dan roti bakar 30000 pakai gopay`  
  Saves two rows automatically if the amounts are explicit.

- `es teh dan roti bakar seharga 20000 pakai gopay`  
  Asks for clarification because one shared total covers multiple items.

- reply `force`  
  Splits the shared total evenly and saves the grouped rows.

### 3. Google Sheets As The Working Ledger

The connected Google Sheet is the working transaction ledger. The bot manages:

- required tabs
- header repair
- grouped row merges for multi-item saves
- category and payment-method seed/setup
- summary sheet rebuilds

### 4. Voice And Image Support

The bot supports:

- Indonesian voice note transcription
- image parsing for receipts and payment screenshots
- provider routing between Gemini and OpenRouter
- OpenRouter model pools with ordered failover and round-robin recovery

### 5. Review, Edit, Delete, And Readback

After a save, the bot can help you correct or remove recent records. It supports:

- edit last transaction
- delete last transaction
- reply-based edit and delete
- read transactions by category and period

### 6. Budget And Comparison Workflows

The bot can:

- set weekly or monthly budgets
- show budget status
- compare this month with the previous month
- summarize spending and income by period

## Commands And What They Do

### Core

- `/start`  
  Claim bot ownership on first use and begin sheet setup.

- `/help`  
  Show a short capability summary and examples.

- `/status`  
  Show owner, active sheet, and setup status.

- `/whoami`  
  Show your Telegram user ID and authorization status.

- `/set_sheet`  
  Start or replace the active Google Sheet connection.

### Period Summaries

- `/today [YYYY-MM-DD]`  
  Show today’s summary or a specific day.

- `/week [YYYY-MM-DD|YYYY-Www]`  
  Show the current week or a specific week.

- `/month [YYYY-MM|MM-YYYY]`  
  Show the current month or a specific month.

- `/moth`  
  Alias for `/month`.

### Transaction Actions

- `/delete_last`  
  Delete the most recent saved transaction.

- `/delete_reply`  
  Delete the transaction represented by the replied bot message.

- `/edit_last <amount> [payment_method]`  
  Edit the most recent saved transaction.

- `/edit_reply <amount> [payment_method]`  
  Edit the transaction represented by the replied bot message.

- `/read <category> <today|week|month>`  
  Read filtered transactions for a category and period.

### Budgeting

- `/budget_set <weekly|monthly> <global|category> <amount> [category]`  
  Create or update a budget rule.

- `/budget_show <weekly|monthly>`  
  Show budget usage and status.

- `/compare_month`  
  Compare the current month with the previous one.

### Setup Utilities

- `/add_payment_method`  
  Add one payment method or wallet label.

- `/add_categories`  
  Add a category row with `type, category, subcategory`.

## Typical Product Workflows

### First-Time Setup

1. Send `/start`
2. The first Telegram user becomes the owner
3. Share a Google Sheet with the service account as `Editor`
4. Send the full Google Sheets link
5. The bot validates the required tabs and starts saving transactions

### Save A Text Transaction

1. Send `beli kopi 25000 pakai bca`
2. The bot parses the message
3. If it is clear enough, it saves the row
4. If not, it asks for confirmation or correction

### Save A Voice Note

1. Send a voice note in Indonesian
2. The bot transcribes it
3. The transcript is parsed into a transaction
4. The result is saved or sent to review depending on confidence

### Save A Screenshot

1. Send a receipt or payment screenshot
2. The bot extracts the transaction details
3. The result is saved or returned for review

### Split A Grouped Purchase

1. Send `es teh 2000 dan roti bakar 30000 pakai gopay`
2. The bot saves multiple rows

If one total is shared:

1. Send `es teh dan roti bakar seharga 20000 pakai gopay`
2. The bot asks for item allocation
3. Reply with explicit amounts or `force`

## Product Rules And Behavior

- only one Telegram owner is allowed to operate the bot
- pending confirmations only continue when you reply to the bot’s confirmation message
- a normal new message is treated as a fresh input, not as confirmation of an older pending state
- Google Sheets remains the working source for transaction history
- Postgres stores bot state, owner identity, reply context, budgets, and learned mappings

## Current Limitations

- grouped multi-item parsing assumes one shared date unless restated
- mixed-provider or mixed-date list inputs are not aggressively split yet
- screenshot parsing quality depends on the provider/model actually handling the image
- summary sheets are rebuilt from backend-generated rows rather than spreadsheet formulas

## Documentation

- Setup: [docs/setup.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/setup.md)
- Development: [docs/development.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/development.md)
- Deployment: [docs/deployment.md](/home/fairuz/Documents/learn/bot-finance-telegram/docs/deployment.md)

## Quick Start

For local development:

```bash
make install
make local-dev
make ngrok-dev
make webhook-set-dev
```

For Docker-based development with Dozzle:

```bash
make docker-dev
```

For production-like Docker runtime:

```bash
make docker-prod
```
