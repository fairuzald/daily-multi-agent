SHELL := /bin/sh

APP_HOST ?= 0.0.0.0
APP_PORT ?= 3000
POETRY ?= poetry
COMPOSE ?= docker compose
UVICORN_APP := api.telegram_webhook:app
DEV_ENV := .env.dev
PROD_ENV := .env
DEV_COMPOSE := -f docker-compose.yml -f docker-compose.dev.yml
PROD_COMPOSE := -f docker-compose.yml
BOT ?= 1

.PHONY: install test local-dev local-prod docker-dev docker-prod docker-down docker-logs docker-logs-dev ngrok-dev webhook-set-dev webhook-info-dev webhook-delete-dev webhook-set-prod webhook-info-prod webhook-delete-prod

define webhook_token
$(if $(filter 2,$(BOT)),$$LIFE_TELEGRAM_BOT_TOKEN,$$TELEGRAM_BOT_TOKEN)
endef

define webhook_path
$(if $(filter 2,$(BOT)),/api/life_telegram_webhook,/api/telegram_webhook)
endef

install:
	$(POETRY) install

test:
	$(POETRY) run python -m pytest -q

local-dev:
	set -a; . ./$(DEV_ENV); set +a; $(POETRY) run uvicorn $(UVICORN_APP) --host $(APP_HOST) --port $(APP_PORT) --reload

local-prod:
	set -a; . ./$(PROD_ENV); set +a; $(POETRY) run uvicorn $(UVICORN_APP) --host $(APP_HOST) --port $(APP_PORT)

docker-dev:
	$(COMPOSE) --env-file $(DEV_ENV) $(DEV_COMPOSE) up --build

docker-prod:
	$(COMPOSE) --env-file $(PROD_ENV) $(PROD_COMPOSE) up --build -d

docker-down:
	$(COMPOSE) --env-file $(DEV_ENV) $(DEV_COMPOSE) down --remove-orphans
	$(COMPOSE) --env-file $(PROD_ENV) $(PROD_COMPOSE) down --remove-orphans

docker-logs:
	$(COMPOSE) --env-file $(PROD_ENV) $(PROD_COMPOSE) logs -f bot

docker-logs-dev:
	$(COMPOSE) --env-file $(DEV_ENV) $(DEV_COMPOSE) logs -f bot dozzle

ngrok-dev:
	ngrok http $(APP_PORT)

webhook-set-dev:
	set -a; . ./$(DEV_ENV); set +a; test -n "$$WEBHOOK_URL"; test -n "$(call webhook_token)"; curl "https://api.telegram.org/bot$(call webhook_token)/setWebhook?url=$$WEBHOOK_URL$(call webhook_path)"

webhook-info-dev:
	set -a; . ./$(DEV_ENV); set +a; test -n "$(call webhook_token)"; curl "https://api.telegram.org/bot$(call webhook_token)/getWebhookInfo"

webhook-delete-dev:
	set -a; . ./$(DEV_ENV); set +a; test -n "$(call webhook_token)"; curl "https://api.telegram.org/bot$(call webhook_token)/deleteWebhook"

webhook-set-prod:
	set -a; . ./$(PROD_ENV); set +a; test -n "$$WEBHOOK_URL"; test -n "$(call webhook_token)"; curl "https://api.telegram.org/bot$(call webhook_token)/setWebhook?url=$$WEBHOOK_URL$(call webhook_path)"

webhook-info-prod:
	set -a; . ./$(PROD_ENV); set +a; test -n "$(call webhook_token)"; curl "https://api.telegram.org/bot$(call webhook_token)/getWebhookInfo"

webhook-delete-prod:
	set -a; . ./$(PROD_ENV); set +a; test -n "$(call webhook_token)"; curl "https://api.telegram.org/bot$(call webhook_token)/deleteWebhook"
