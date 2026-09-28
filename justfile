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

# Follow the logs of every service
gateway-logs:
    docker compose logs --follow

# Call the gateway with the OpenAI SDK and check the local model answers
smoke: _env
    uv run --no-project --with openai python scripts/smoke_test.py

# Run the tests (smoke test for now)
test: smoke

[private]
_env:
    #!/usr/bin/env sh
    if [ ! -f .env ]; then
        cp .env.example .env
        echo "Created .env from .env.example: change the secrets before any shared use."
    fi
