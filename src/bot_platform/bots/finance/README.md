# Finance Bot

Private Telegram finance bot for Indonesian daily money tracking.

## Product Capabilities

- natural-language-first understanding for text, voice notes, screenshots, and reply follow-ups
- one unified AI extractor prompt for the live finance message flow
- parse expenses, income, transfers, and investment flows
- understand common Indonesian amount shorthand such as `3k`, `25rb`, `3jt`, `3 juta`, and `3mil`
- use reply context for edit/delete/follow-up cases like `ubah ini`, `hapus ini`, `pakai gopay`, or `saya juga beli ...`
- when the user replies to an existing transaction without explicit edit/delete intent, the bot can append a new row and inherit missing fields such as date, payment method, or category from the replied transaction
- ask for clarification when intent or fields are still ambiguous
- save into Google Sheets
- use AI with provider fallback
- keep pending confirmation state for low-confidence transactions
- generate today, week, month, budget, read, and comparison summaries

## Main Commands

- `/start`
- `/help`
- `/full_help`
- `/fullhelp`
- `/whoami`
- `/status`
- `/set_sheet`
- `/add_payment_method`
- `/add_categories`
- `/today`
- `/week`
- `/month`
- `/delete_last`
- `/delete_reply`
- `/edit_last`
- `/edit_reply`
- `/read`
- `/budget_set`
- `/budget_show`
- `/compare_month`

Commands are optional for most day-to-day use. Natural language is the primary path.

## Main Inputs

- `beli kopi 25000 pakai bca`
- `makan siang 45000 kemarin pakai gopay`
- `ubah ini jadi 35rb pakai gopay`
- `hapus ini`
- reply to a saved row with `saya juga beli telur 8000`
- `beri summary selama 1 bulan`
- `bandingkan bulan ini sama bulan lalu`
- voice note in Indonesian
- receipt or payment screenshot

## Current Finance Flow

- user sends text, voice, or image
- one unified extractor interprets the message
- if the message replies to an existing transaction, the extractor decides whether it means edit/delete or a new transaction that should inherit shared context
- deterministic enrichment validates dates, amounts, and learned mappings
- inherited reply-context dates are preserved unless the new message explicitly overrides the date
- if confidence is low, the bot asks for clarification instead of guessing
- if confidence is good, the transaction is saved and the bot replies with a human-readable summary

## First Use

- send `/start` first to claim the bot in that environment
- if the bot asks for sheet setup, share the sheet with the service account email and send the sheet link
- use `/whoami` if you need to verify the stored owner and chat IDs

## Related Docs

- Setup: [SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/SETUP.md)
- Development: [DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/DEVELOPMENT.md)
