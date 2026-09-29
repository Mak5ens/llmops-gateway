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

# Start LiteLLM, PostgreSQL, Ollama and Presidio, wait until they are healthy, then create the client teams and keys
gateway-up: _env
    docker compose up --detach --wait
    docker compose run --rm --no-deps tenants-bootstrap
    @echo "Gateway ready on http://localhost:${LITELLM_PORT:-4000} (try: just smoke)"

# Stop the stack (pass --volumes to also delete the database and the models)
gateway-down *args:
    docker compose down {{ args }}

# Restart LiteLLM to apply changes to config/litellm.yaml
gateway-reload:
    docker compose restart litellm
    docker compose up --detach --wait litellm

# Apply config/tenants.yaml (teams, budgets, keys) to the running gateway; safe to re-run
tenants:
    docker compose run --rm --no-deps tenants-bootstrap

# Follow the logs of every service
gateway-logs:
    docker compose logs --follow

# Call every alias with a team key: a quick check after `just gateway-reload`
smoke: _env
    uv run pytest tests/test_routing.py

# Run the integration tests (starts the stack if needed); pass pytest arguments, e.g. `just test -k budget`
test *args: _env
    uv run pytest {{ args }}

[private]
_env:
    #!/usr/bin/env sh
    if [ ! -f .env ]; then
        cp .env.example .env
        echo "Created .env from .env.example: change the secrets before any shared use."
    fi
