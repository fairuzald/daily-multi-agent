# Bot Pipelines

This document explains the current end-to-end processing flow for both bots.

- Image asset: [bot-pipelines.svg](/home/fairuz/Documents/learn/bot-finance-telegram/docs/assets/bot-pipelines.svg)

## Finance Bot

High-level flow:

1. Telegram controller receives text, voice, or image.
2. Voice is transcribed first.
3. Message entry service checks setup mode and pending confirmation state.
4. AI intent interpreter decides whether the message is:
   - a new transaction
   - edit
   - delete
   - summary
   - comparison
   - budget/read command
   - clarification
5. If the intent is an action, command service executes it.
6. If the intent is a transaction, the bot runs multi-transaction detection or single-transaction parsing.
7. Deterministic enrichment resolves dates, learned mappings, and normalization.
8. Policy validation decides whether to:
   - ask for clarification
   - save immediately
9. Persistence writes the transaction to Google Sheets and updates bot state.
10. The bot returns a human-readable confirmation or summary.

Core files:

- Entry flow: [message_entry_service.py](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/application/message_entry_service.py:1)
- Unified extraction schema: [extraction.py](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/domain/extraction.py:1)
- Unified extraction prompt: [finance_message_extractor.txt](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/prompts/finance_message_extractor.txt:1)
- Command execution: [command_service.py](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/application/command_service.py:1)
- Transaction enrichment/querying: [transaction_query_service.py](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/application/transaction_query_service.py:1)
- Save/clarification policy: [policies.py](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/finance/domain/policies.py:1)

## Life Bot

High-level flow:

1. Telegram controller receives text or voice.
2. Voice is transcribed first.
3. Message service checks reply context and pending parse/confirmation state.
4. Inline actions are handled first:
   - done
   - snooze
   - cancel
   - view
   - edit
5. If the message is not an inline action, the AI parser or deterministic parser extracts life items.
6. The bot decides whether the result needs confirmation or manual rewrite.
7. If confirmed, item service saves the item and optionally syncs to Google Calendar.
8. The bot returns a human-readable result.

Core files:

- Entry flow: [message_service.py](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/application/message_service.py:1)
- Item actions: [item_service.py](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/application/item_service.py:1)
- Rendering: [rendering.py](/home/fairuz/Documents/learn/bot-finance-telegram/src/bot_platform/bots/life/application/rendering.py:1)

## Mermaid

```mermaid
flowchart TD
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
```
