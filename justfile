# Load .env so recipes see LITELLM_MASTER_KEY and LITELLM_PORT.
set dotenv-load

# List recipes
default:
    @just --list

# Install the git hooks (pre-commit and commit-msg)
hooks:
    pre-commit install

# Run every pre-commit check on all files
lint:
    pre-commit run --all-files

# Start LiteLLM, PostgreSQL and Ollama, and wait until they are healthy
gateway-up: _env
    docker compose up --detach --wait
    @echo "Gateway ready on http://localhost:${LITELLM_PORT:-4000} (try: just smoke)"

# Stop the stack (pass --volumes to also delete the database and the models)
gateway-down *args:
    docker compose down {{ args }}

# Restart LiteLLM to apply changes to config/litellm.yaml
gateway-reload:
    docker compose restart litellm
    docker compose up --detach --wait litellm

# Follow the logs of every service
gateway-logs:
    docker compose logs --follow

# Call every alias (chat-small, chat-large, embed) with the OpenAI SDK
smoke: _env
    uv run --no-project --with openai python scripts/smoke_test.py

# Stop ollama-large, check chat-large falls back to chat-small within 30 s, then restart it
fallback-test: _env
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'docker compose start ollama-large >/dev/null 2>&1' EXIT
    uv run --no-project --with openai python scripts/fallback_test.py
    echo "Gateway logs:"
    docker compose logs --since 45s --no-log-prefix litellm | grep -E "Exception|fallback" | cut -c1-160

# Run every test
test: smoke fallback-test

[private]
_env:
    #!/usr/bin/env sh
    if [ ! -f .env ]; then
        cp .env.example .env
        echo "Created .env from .env.example: change the secrets before any shared use."
    fi
