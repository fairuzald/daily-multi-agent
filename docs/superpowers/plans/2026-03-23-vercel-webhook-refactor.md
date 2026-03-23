# Vercel Webhook Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Telegram finance bot deployable on Vercel via webhook while preserving the current local polling workflow.

**Architecture:** Extract shared Telegram application construction into a reusable runtime module, keep `src/bot_finance_telegram/app.py` as the local polling runner, and add a Vercel Python function entrypoint under `api/` to process Telegram webhook POST requests. Reuse the existing handlers and services so only the transport layer changes.

**Tech Stack:** Python 3.11, python-telegram-bot, Poetry, Vercel Python Functions, Postgres, Gemini, Google Sheets

---

## File Structure

- Create: `src/bot_finance_telegram/runtime.py`
  - shared builder/helpers for Telegram application and service wiring
- Create: `api/telegram_webhook.py`
  - Vercel-compatible webhook handler
- Create: `vercel.json`
  - route and runtime config if needed
- Modify: `src/bot_finance_telegram/app.py`
  - keep local polling entrypoint, delegate construction to shared runtime
- Modify: `README.md`
  - document local polling, Vercel deployment, env vars, webhook registration
- Modify: `tests/test_app.py`
  - adapt local tests if app builder changes
- Create or Modify: `tests/test_webhook.py`
  - webhook transport tests

## Chunk 1: Shared Runtime Extraction

### Task 1: Add the failing shared-runtime tests

**Files:**
- Modify: `tests/test_app.py`
- Create: `tests/test_webhook.py`

- [ ] **Step 1: Write a failing test for reusable application construction**

Add a test that imports a shared runtime builder and asserts it returns a Telegram application with bot handlers attached.

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
poetry run env PYTHONPATH=src python -m pytest -q tests/test_app.py tests/test_webhook.py
```

Expected: FAIL because `runtime.py` or webhook entrypoint does not exist yet.

- [ ] **Step 3: Create `src/bot_finance_telegram/runtime.py`**

Implement:

- settings-driven service wiring
- shared Telegram application creation
- helper to retrieve bot handlers from app state

- [ ] **Step 4: Refactor `src/bot_finance_telegram/app.py` to use the shared runtime**

Keep:

- local polling command
- dev-mode reload behavior

Move only the construction logic out.

- [ ] **Step 5: Run the targeted tests again**

Run:

```bash
poetry run env PYTHONPATH=src python -m pytest -q tests/test_app.py tests/test_webhook.py
```

Expected: local runtime construction tests pass or move to the next missing webhook failure.

- [ ] **Step 6: Commit**

```bash
git add src/bot_finance_telegram/runtime.py src/bot_finance_telegram/app.py tests/test_app.py tests/test_webhook.py
git commit -m "refactor: extract shared telegram runtime"
```

## Chunk 2: Vercel Webhook Transport

### Task 2: Add the webhook entrypoint

**Files:**
- Create: `api/telegram_webhook.py`
- Create: `vercel.json`
- Test: `tests/test_webhook.py`

- [ ] **Step 1: Write the failing webhook transport tests**

Cover:

- POST with Telegram update JSON returns HTTP 200
- invalid method or malformed body returns a safe error status
- webhook path delegates into shared Telegram processing

- [ ] **Step 2: Run webhook tests to verify failure**

Run:

```bash
poetry run env PYTHONPATH=src python -m pytest -q tests/test_webhook.py
```

Expected: FAIL because the webhook file does not yet exist or the handler is incomplete.

- [ ] **Step 3: Implement `api/telegram_webhook.py`**

Build a minimal Vercel Python function that:

- reads request method/body
- creates Telegram `Update`
- initializes or reuses the shared Telegram application
- processes the update
- returns HTTP 200 JSON/plain response

- [ ] **Step 4: Add `vercel.json` only if routing/runtime config is required**

Keep it minimal. Do not add unnecessary rewrites if Vercel’s default Python behavior is sufficient.

- [ ] **Step 5: Re-run webhook tests**

Run:

```bash
poetry run env PYTHONPATH=src python -m pytest -q tests/test_webhook.py
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/telegram_webhook.py vercel.json tests/test_webhook.py
git commit -m "feat: add vercel telegram webhook entrypoint"
```

## Chunk 3: Runtime Compatibility and Docs

### Task 3: Preserve local behavior and document deployment

**Files:**
- Modify: `README.md`
- Modify: `src/bot_finance_telegram/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Add tests proving local polling entrypoint still works**

Cover:

- app creation still validates required env
- polling runner still uses the shared runtime

- [ ] **Step 2: Run targeted local runtime tests**

Run:

```bash
poetry run env PYTHONPATH=src python -m pytest -q tests/test_app.py
```

Expected: PASS after adjustments.

- [ ] **Step 3: Update `README.md`**

Document:

- local polling command
- Vercel deployment model
- required env vars
- need for hosted Postgres on Vercel
- Telegram webhook registration command

- [ ] **Step 4: Run a full verification pass**

Run:

```bash
poetry run env PYTHONPATH=src python -m pytest -q
```

Expected: PASS

- [ ] **Step 5: Run syntax verification**

Run:

```bash
poetry run env PYTHONPATH=src python -m py_compile $(rg --files -g '*.py' src tests api)
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add README.md src/bot_finance_telegram/app.py tests/test_app.py
git commit -m "docs: document local polling and vercel webhook deployment"
```

## Execution Notes

- Keep local polling as the default developer workflow.
- Do not remove Docker Compose in this pass.
- Do not migrate in-memory reply context to persistent storage unless the webhook path forces it.
- If `python-telegram-bot` webhook processing requires a different lifecycle than expected, prefer a thin compatibility adapter over rewriting bot logic.

Plan complete and saved to `docs/superpowers/plans/2026-03-23-vercel-webhook-refactor.md`. Ready to execute?
