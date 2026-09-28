.DEFAULT_GOAL := help
.PHONY: help hooks lint gateway-up gateway-down gateway-logs smoke up down test

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-13s %s\n", $$1, $$2}'

hooks: ## Install the git hooks (pre-commit and commit-msg)
	pre-commit install

lint: ## Run every pre-commit check on all files
	pre-commit run --all-files

.env:
	cp .env.example .env
	@echo "Created .env from .env.example: change the secrets before any shared use."

gateway-up: .env ## Start LiteLLM, PostgreSQL and Ollama, and wait until they are healthy
	docker compose up --detach --wait
	@echo "Gateway ready on http://localhost:$${LITELLM_PORT:-4000} (try: make smoke)"

gateway-down: ## Stop the stack (add ARGS=--volumes to also delete the database and the models)
	docker compose down $(ARGS)

gateway-logs: ## Follow the logs of every service
	docker compose logs --follow

smoke: .env ## Call the gateway with the OpenAI SDK and check the local model answers
	set -a && . ./.env && set +a && uv run --no-project --with openai python scripts/smoke_test.py

up: gateway-up ## Alias of gateway-up

down: gateway-down ## Alias of gateway-down

test: smoke ## Run the tests (smoke test for now)
