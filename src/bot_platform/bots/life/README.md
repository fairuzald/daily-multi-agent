# Life Bot

Private Telegram life admin bot for:

- tasks
- reminders
- follow-ups
- important dates

## Product Capabilities

- AI-first natural-language parsing
- one unified extraction prompt for new messages and rewrites
- one message can create multiple items
- voice note support through transcription
- reply-based actions on saved items
- Google Calendar sync for dated items
- Telegram reminders through the reminder tick endpoint
- pending rewrite mode when parsing is unsafe
- recurring reminders with `until` end-date support

## Item Types

- `task`
- `reminder`
- `follow_up`
- `important_date`

## Main Commands

- `/start`
- `/help`
- `/whoami`
- `/status`
- `/today` = only today
- `/tomorrow` = only tomorrow
- `/upcoming` = next 7 days, including tomorrow
- `/overdue`
- `/followups`
- `/dates`
- `/done` = latest active item, or reply to a saved item
- `/view` or `/detail` = latest active item, or reply to a saved item
- `/edit` or `/ubah` = edit by reply or item id
- `/snooze 2hours` = latest active item, or reply to a saved item
- `/cancel` = latest active item, or reply to a saved item
- `/delete` = same behavior as cancel

## Good Inputs

- `bayar wifi besok jam 9`
- `ingatkan cek transfer 5 menit lagi`
- `follow up Aldi Selasa depan jam 8 malam`
- `ulang tahun ibu 12 Mei`
- `bayar kos tiap bulan sampai 30 Mei 2026`
- `bayar wifi besok dan follow up Aldi Jumat jam 8 malam`

## Current Life Flow

- user sends text or voice
- one unified extractor interprets the message or rewrite
- if parsing is safe, items are saved immediately
- if the message is still unclear, the bot stores a pending rewrite context and asks for a clearer version
- reply-based actions like `done`, `hapus ini`, `detail ini`, `ubah jadi ...`, and `snooze 2hours` are handled on top of saved item context

## First Use

- send `/start` first to claim the bot in that environment
- use `/whoami` if you need to verify the stored owner and chat IDs

## Related Docs

- Setup: [SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)
- Development: [DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/DEVELOPMENT.md)
