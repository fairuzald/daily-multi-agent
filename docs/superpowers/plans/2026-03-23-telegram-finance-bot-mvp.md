# Telegram Finance Bot MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MVP personal finance Telegram bot that accepts Indonesian text and voice inputs, parses transactions with Gemini, writes structured data into Google Sheets, and generates a monthly summary sheet plus improvement insights.

**Architecture:** The bot will be implemented as a Python application with clear service boundaries for Telegram handling, Gemini parsing, Google Sheets persistence, and summary generation. A thin application layer will orchestrate the flow from inbound message to parsed transaction to spreadsheet write while keeping domain logic separate from API clients.

**Tech Stack:** Python 3.12, `python-telegram-bot`, Google Sheets API via `gspread`, Gemini API client, `pydantic`, `python-dotenv`, `pytest`

---

## File Structure

- Create: `src/bot_finance_telegram/__init__.py`
- Create: `src/bot_finance_telegram/config.py`
- Create: `src/bot_finance_telegram/models.py`
- Create: `src/bot_finance_telegram/categories.py`
- Create: `src/bot_finance_telegram/services/gemini_client.py`
- Create: `src/bot_finance_telegram/services/sheets_client.py`
- Create: `src/bot_finance_telegram/services/summary_service.py`
- Create: `src/bot_finance_telegram/services/state_store.py`
- Create: `src/bot_finance_telegram/handlers.py`
- Create: `src/bot_finance_telegram/app.py`
- Create: `src/bot_finance_telegram/prompts/transaction_parser.txt`
- Create: `scripts/bootstrap_sheet.py`
- Create: `tests/test_models.py`
- Create: `tests/test_summary_service.py`
- Create: `tests/test_handlers.py`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `README.md`

## Chunk 1: Project Skeleton And Domain Models

### Task 1: Create dependency manifest and environment template

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `README.md`

- [ ] **Step 1: Write the failing expectations as a checklist in README**
- [ ] **Step 2: Add dependencies for Telegram, Gemini, Sheets, config, and tests**
- [ ] **Step 3: Add required environment variables with placeholder values**
- [ ] **Step 4: Document local setup commands**
- [ ] **Step 5: Commit**

### Task 2: Define core finance models

**Files:**
- Create: `src/bot_finance_telegram/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for transaction normalization and validation**

```python
def test_transfer_requires_both_accounts():
    ...

def test_expense_defaults_currency_to_idr():
    ...
```

- [ ] **Step 2: Run `pytest tests/test_models.py -v` and confirm failure**
- [ ] **Step 3: Implement pydantic models for transactions, summaries, and insights**
- [ ] **Step 4: Run `pytest tests/test_models.py -v` and confirm pass**
- [ ] **Step 5: Commit**

## Chunk 2: External Service Clients

### Task 3: Build Gemini transaction parsing client

**Files:**
- Create: `src/bot_finance_telegram/services/gemini_client.py`
- Create: `src/bot_finance_telegram/prompts/transaction_parser.txt`

- [ ] **Step 1: Add prompt template for Indonesian transaction parsing**
- [ ] **Step 2: Implement client method for parsing text or transcript into normalized JSON**
- [ ] **Step 3: Implement a stubbed transcription interface for future audio integration**
- [ ] **Step 4: Add error handling for invalid AI output**
- [ ] **Step 5: Commit**

### Task 4: Build Google Sheets client and bootstrap script

**Files:**
- Create: `src/bot_finance_telegram/services/sheets_client.py`
- Create: `scripts/bootstrap_sheet.py`

- [ ] **Step 1: Define tab schemas and header rows**
- [ ] **Step 2: Implement append transaction and replace summary methods**
- [ ] **Step 3: Implement helper methods to read categories, budgets, and accounts**
- [ ] **Step 4: Add bootstrap script to create the agreed tabs and headers**
- [ ] **Step 5: Commit**

## Chunk 3: Summary Generation

### Task 5: Implement monthly summary generation

**Files:**
- Create: `src/bot_finance_telegram/services/summary_service.py`
- Create: `tests/test_summary_service.py`

- [ ] **Step 1: Write failing tests for monthly totals, category rollups, and improvement insights**
- [ ] **Step 2: Run `pytest tests/test_summary_service.py -v` and confirm failure**
- [ ] **Step 3: Implement monthly overview, category summaries, income source summaries, and balance calculations**
- [ ] **Step 4: Implement improvement insight rules for overspending, high concentration, recurring costs, and savings rate**
- [ ] **Step 5: Run `pytest tests/test_summary_service.py -v` and confirm pass**
- [ ] **Step 6: Commit**

## Chunk 4: Telegram Application Flow

### Task 6: Build command and message handlers

**Files:**
- Create: `src/bot_finance_telegram/handlers.py`
- Create: `src/bot_finance_telegram/services/state_store.py`
- Create: `tests/test_handlers.py`

- [ ] **Step 1: Write failing tests for text transaction intake and `/month` output**
- [ ] **Step 2: Run `pytest tests/test_handlers.py -v` and confirm failure**
- [ ] **Step 3: Implement slash commands and plain-text intake flow**
- [ ] **Step 4: Implement confirmation/edit/delete state handling**
- [ ] **Step 5: Implement monthly summary command using the summary service**
- [ ] **Step 6: Run `pytest tests/test_handlers.py -v` and confirm pass**
- [ ] **Step 7: Commit**

### Task 7: Wire the application entrypoint

**Files:**
- Create: `src/bot_finance_telegram/config.py`
- Create: `src/bot_finance_telegram/app.py`

- [ ] **Step 1: Implement environment-backed settings**
- [ ] **Step 2: Construct service clients and inject them into handlers**
- [ ] **Step 3: Expose a `main()` entrypoint for local execution**
- [ ] **Step 4: Add a short startup check for required configuration**
- [ ] **Step 5: Commit**

## Chunk 5: Verification And Handoff

### Task 8: Verify baseline behavior and polish documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run `pytest -q`**
- [ ] **Step 2: Run a local import smoke test**
- [ ] **Step 3: Update README with setup, bootstrap, and bot usage examples**
- [ ] **Step 4: Record known limitations for voice-note implementation details**
- [ ] **Step 5: Commit**
