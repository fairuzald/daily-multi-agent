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
- `/snooze 2hours` = latest active item, or reply to a saved item
- `/cancel` = latest active item, or reply to a saved item
- `/delete` = same behavior as cancel

## Good Inputs

- `pay wifi tomorrow 9am`
- `remind me in 5 minutes to check transfer`
- `follow up with Aldi next Tuesday 8pm`
- `mom birthday 12 May`
- `pay wifi tomorrow and follow up with Aldi on Friday 8pm`

## First Use

- send `/start` first to claim the bot in that environment
- use `/whoami` if you need to verify the stored owner and chat IDs

## Related Docs

- Setup: [SETUP.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/SETUP.md)
- Development: [DEVELOPMENT.md](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/DEVELOPMENT.md)
