# Telegram Finance Bot Design

**Goal:** Build a personal finance Telegram bot that accepts Indonesian text and voice notes, parses transactions with Gemini, stores them in Google Sheets, and produces monthly summaries plus improvement insights.

## Product Scope

This bot is for personal finance only. It should capture daily expenses, income, and transfers in a way that is fast enough for casual use in Telegram but structured enough to support summaries, balances, budgets, and recommendations in Google Sheets.

The first version should prioritize reliable transaction capture over advanced automation. Double-entry bookkeeping and complex accounting workflows are intentionally out of scope.

## Core User Flows

### 1. Transaction capture by text

The user sends a natural-language chat message such as `beli makan siang 35 ribu pakai gopay` or `gaji masuk 8 juta`.

The bot sends the message to Gemini for extraction, normalizes the result into one structured transaction, asks one follow-up question when required fields are missing, and appends a row to Google Sheets.

### 2. Transaction capture by Indonesian voice note

The user sends a Telegram voice note in Indonesian. The bot downloads the file, obtains a transcript, parses the transcript into a transaction, stores the original transcript in the ledger, and writes the result to Google Sheets.

If confidence is too low, the bot must ask for confirmation instead of silently saving incorrect data.

### 3. Review and correction

The user can inspect current-day or current-month results and correct mistakes with targeted commands such as editing or deleting the last transaction.

### 4. Monthly review

The bot summarizes total income, total expenses, net cash flow, category spending, balance changes, budget status, and improvement suggestions for the current month.

## Functional Requirements

### Supported transaction types

- Expense
- Income
- Transfer

### Input methods

- Free-form text
- Voice notes in Indonesian
- Explicit slash commands for cases where the user wants to force the transaction type

### Bot commands

- `/start`
- `/help`
- `/add`
- `/income`
- `/expense`
- `/transfer`
- `/today`
- `/month`
- `/balance`
- `/budget`
- `/edit_last`
- `/delete_last`
- `/categories`
- `/accounts`

### Parsing rules

Gemini must support informal Indonesian amount and time expressions including:

- `goceng`
- `ceban`
- `ribu`
- `juta`
- `hari ini`
- `kemarin`
- `tadi pagi`
- `tadi malam`
- `barusan`

The parser must return normalized JSON. Missing fields must be surfaced explicitly so the bot can ask a follow-up question.

## Google Sheets Data Model

### Transactions tab

Required columns:

- `transaction_id`
- `created_at`
- `transaction_date`
- `type`
- `amount`
- `currency`
- `category`
- `subcategory`
- `account_from`
- `account_to`
- `merchant_or_source`
- `description`
- `payment_method`
- `tags`
- `input_mode`
- `raw_input`
- `ai_confidence`
- `status`

### Accounts tab

Required columns:

- `account_id`
- `account_name`
- `account_type`
- `currency`
- `opening_balance`
- `current_balance`
- `is_active`
- `notes`

### Categories tab

Required columns:

- `category_id`
- `type`
- `category_name`
- `subcategory_name`
- `budget_limit`
- `keywords`
- `is_active`

### Budgets tab

Required columns:

- `budget_id`
- `month`
- `category_name`
- `budget_amount`
- `spent_amount`
- `remaining_amount`
- `alert_threshold`
- `notes`

### Recurring tab

Required columns:

- `recurring_id`
- `title`
- `type`
- `amount`
- `category`
- `account_from`
- `account_to`
- `merchant_or_source`
- `schedule`
- `next_due_date`
- `auto_record`
- `is_active`
- `notes`

### Summary tab

The summary tab should be generated from transaction data and present:

- Monthly overview
- Expense by category
- Income by source
- Account balances
- Recurring costs
- Improvement insights

## Architecture

### Telegram layer

The Telegram bot receives text messages and voice notes, exposes slash commands, and sends short follow-up prompts or confirmations.

### AI layer

Gemini is responsible for transcription-parsing workflow support. The first implementation should treat transcription and transaction extraction as separate services so either can be adjusted independently later.

### Persistence layer

Google Sheets is the source of truth for finance data. A lightweight local persistence layer is still useful for transient bot state such as edit/delete references, pending confirmations, or setup progress.

### Reporting layer

Monthly summaries can be computed in the backend and then pushed into the `Summary` sheet in a predictable tabular layout. This avoids forcing complex spreadsheet formulas into the initial version.

## Error Handling

- If transcription fails, tell the user and ask them to resend or type the transaction.
- If parsing confidence is low, ask a targeted clarification question.
- If Google Sheets write fails, do not claim the transaction was saved.
- If a category or account is unknown, fall back to a neutral placeholder and ask for confirmation.

## Non-Goals

- Double-entry bookkeeping
- Multi-user support
- Receipt OCR
- Bank account syncing
- Tax reporting

## Success Criteria

- User can log expenses, income, and transfers from Telegram.
- Indonesian voice notes are transcribed and converted into structured rows.
- Data lands in the expected Google Sheets tabs.
- The user can request a monthly summary and receive actionable improvement suggestions.
