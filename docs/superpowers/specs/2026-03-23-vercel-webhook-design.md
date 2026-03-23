# Vercel Webhook Refactor Design

## Goal

Make the Telegram finance bot deployable on Vercel while preserving the current local development workflow based on Telegram polling.

## Current Context

The project currently runs as a long-lived polling worker through `python-telegram-bot` in [`src/bot_finance_telegram/app.py`](./../../src/bot_finance_telegram/app.py). That fits Docker, VMs, and worker platforms, but not Vercel. Vercel requires request/response-style functions, so Telegram updates must arrive through a webhook endpoint instead of an always-on polling loop.

The existing business logic already lives in handlers and services:

- Telegram transport: `src/bot_finance_telegram/app.py`
- Bot workflow logic: `src/bot_finance_telegram/handlers.py`
- Gemini integration: `src/bot_finance_telegram/services/gemini_client.py`
- Sheets integration: `src/bot_finance_telegram/services/sheets_client.py`
- State persistence: `src/bot_finance_telegram/services/state_store.py`

That split is good enough to support a transport refactor without rewriting the finance logic.

## Recommended Approach

Use a dual-runtime design:

1. Keep polling for local development.
2. Add a webhook HTTP entrypoint for Vercel production.
3. Reuse the same `BotHandlers` and service layer in both modes.

This is the best tradeoff because it avoids forcing local development through tunnels and webhook registration while still making the production path compatible with Vercel’s execution model.

## Alternatives Considered

### 1. Webhook Only

Pros:
- Single production-style runtime
- Fewer transport branches

Cons:
- Local development becomes slower and more fragile
- Requires tunnel/webhook setup every time
- Worse fit for current workflow

### 2. Dual Runtime

Pros:
- Preserves current local command
- Adds Vercel compatibility cleanly
- Finance logic stays shared

Cons:
- Slightly more transport-layer code
- Need to document two runtime modes

### 3. Separate Local and Vercel Apps

Pros:
- Clear physical separation

Cons:
- Duplicated routing and lifecycle logic
- Higher maintenance cost

## Architecture

### Transport Split

Refactor the current app entrypoint into three layers:

1. `bot runtime builder`
   - Creates shared services and a reusable `python-telegram-bot` `Application`
2. `polling runner`
   - Used locally and in Docker
3. `webhook adapter`
   - Used by Vercel as an HTTP function

The webhook adapter should:

- Accept Telegram webhook POST requests
- Deserialize the update body
- Pass the update into the existing Telegram application/dispatcher
- Return a fast HTTP success response

### Suggested File Structure

- Keep: `src/bot_finance_telegram/app.py`
  - local polling entrypoint
- Create: `src/bot_finance_telegram/runtime.py`
  - shared application construction and lifecycle helpers
- Create: `api/telegram_webhook.py`
  - Vercel Python function entrypoint
- Create: `vercel.json`
  - optional routing/runtime config if needed

### Runtime Modes

Add a lightweight mode split:

- local default: polling
- Vercel default: webhook

This can be controlled by environment or simply by using different entrypoints:

- local: `python -m bot_finance_telegram.app`
- vercel: `api/telegram_webhook.py`

Entry-point separation is preferable to overloading one file with too many runtime branches.

## Webhook Flow

1. Telegram sends POST to `/api/telegram_webhook`
2. Vercel Python function receives JSON body
3. JSON is converted into Telegram `Update`
4. Shared application processes the update
5. Existing handlers run:
   - auth
   - sheet setup
   - text/voice/image parsing
   - corrections
   - summaries
6. Bot replies are sent using the Telegram Bot API through the normal library client
7. Function returns HTTP 200

## Local Flow

Local behavior should not change:

```bash
poetry run python -m bot_finance_telegram.app
```

That should still run polling, hot reload in dev mode, and the existing Docker-based workflow.

## Error Handling

The existing user-facing error translation should be preserved in both transports:

- Gemini quota exhausted
- upstream timeout
- permission/service errors
- generic processing failures

The webhook adapter should never expose raw tracebacks to Telegram or the HTTP client.

## State and Dependencies

### Database

Vercel cannot use the local Docker Postgres. Production on Vercel must point `DATABASE_URL` at hosted Postgres.

### Google Sheets and Gemini

No change in functional behavior:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GEMINI_API_KEY`
- `TELEGRAM_BOT_TOKEN`

remain required.

### Telegram Webhook Registration

Need a documented setup step to register the webhook URL with Telegram, for example:

```text
https://api.telegram.org/bot<token>/setWebhook?url=https://<project>.vercel.app/api/telegram_webhook
```

This should be documented, not necessarily automated in the first pass.

## Testing Strategy

Add tests at the transport boundary:

- webhook request with valid Telegram JSON returns 200
- webhook passes update into shared bot logic
- local polling path still constructs the application correctly

Existing handler/service tests should remain unchanged wherever possible.

## Risks

### 1. `python-telegram-bot` webhook lifecycle on serverless

Need to ensure the chosen integration works in a stateless request environment without assuming a long-running process.

### 2. Cold start and API latency

Voice/image parsing can be slower than text. The function path should return reliably within Vercel limits.

### 3. In-memory reply context

The app currently keeps some reply contexts in memory. On serverless, warm instance reuse is not guaranteed, so reply behavior across cold starts may be less reliable unless migrated to persistent storage later.

This is not a blocker for the transport refactor, but it should be called out as a runtime caveat.

## Non-Goals

The Vercel refactor should not:

- redesign finance logic
- redesign Google Sheets schema
- replace Gemini
- migrate all in-memory state to Postgres in the same change unless strictly required by the webhook path

## Recommended First Implementation Scope

1. Extract shared runtime/application builder
2. Add Vercel webhook entrypoint
3. Preserve local polling command
4. Add docs for Vercel deploy + webhook registration
5. Add webhook transport tests
