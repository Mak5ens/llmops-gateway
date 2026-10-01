# Load .env so recipes see LITELLM_MASTER_KEY and LITELLM_PORT.
set dotenv-load
# Pass recipe arguments as "$@", so a quoted argument like `-m "not leak"` stays one argument.
set positional-arguments

# List recipes
default:
    @just --list

# Install the git hooks (pre-commit and commit-msg)
hooks:
    pre-commit install

# Run every pre-commit check on all files
lint:
    pre-commit run --all-files

# Start LiteLLM, PostgreSQL, Ollama, Presidio and Langfuse, wait until they are healthy, then create the client teams and keys
gateway-up: _env
    docker compose up --detach --wait --build
    docker compose run --rm --no-deps tenants-bootstrap
    @echo "Gateway ready on http://localhost:${LITELLM_PORT:-4000} (try: just smoke)"

# Stop the stack (pass --volumes to also delete the databases, the Langfuse traces and the models)
gateway-down *args:
    docker compose down "$@"

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
    uv run pytest tests/integration/test_routing.py

# Run every test (starts the stack if needed); pass pytest arguments, e.g. `just test -k budget`
test *args: _env
    uv run pytest "$@"

# Run the unit tests of the Presidio recognizers and of the guardrail class: no stack, a few seconds
test-unit *args:
    uv run pytest tests/unit "$@"

# Benchmark the anonymization (Presidio against local LLMs, latency of the guardrail) into benchmarks/results.md.
# Downloads qwen2.5:7b (4.7 GB) on first run and takes about 30 minutes on CPU; `--skip-llm` takes 10 seconds.
gateway-bench *args: gateway-up
    uv run python benchmarks/run_bench.py "$@"

[private]
_env:
    #!/usr/bin/env sh
    if [ ! -f .env ]; then
        cp .env.example .env
        echo "Created .env from .env.example: change the secrets before any shared use."
    fi
