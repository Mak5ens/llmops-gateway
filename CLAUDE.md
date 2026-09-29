# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

`llmops-gateway` is block 1 of a portfolio "internal AI platform": the single entry point to every LLM. LiteLLM Proxy handles per-team virtual keys, budgets, rate limiting and routing. A Presidio pre-call hook anonymizes French PII before inference and re-identifies the answer. Self-hosted Langfuse traces every call with its cost per team. Ollama serves models locally; vLLM replaces it once the gateway moves to Kubernetes in the sibling repo `llmops-platform`.

Planning lives in Linear (team key `LAB`, project "Plateforme IA · Gateway d'entreprise"). The cross-cutting vision document is "Portfolio IA — Vision, architecture et conventions".

## Current state

Milestone 1.1 is done; milestone 1.2 (Presidio) is in progress. `compose.yaml` runs LiteLLM Proxy (`litellm-database` image, which applies its Prisma migrations to PostgreSQL at startup), PostgreSQL and two Ollama servers sharing one model volume: `ollama` serves `chat-small` and `embed`, `ollama-large` serves `chat-large`, so stopping it simulates an outage of one model server. A one-shot `ollama-pull` service downloads every model in `OLLAMA_MODELS` before LiteLLM starts. Presidio Analyzer and Anonymizer run in the stack but LiteLLM does not call them yet (LAB-115). Langfuse (LAB-117) is not in the stack yet.

Routing lives in `config/litellm.yaml`: callers only use usage aliases (`chat-small`, `chat-large`, `embed`), and `chat-large` falls back to `chat-small`. Things learned the hard way, keep them in mind when touching it:

- LiteLLM reads the file only at startup: run `just gateway-reload` after editing it, or the old model list stays loaded.
- A pooled connection to a server that died hangs until the model `timeout`, so that timeout is the worst-case failover time. `chat-large` has `num_retries: 0` because each retry waits the full timeout again. `retry_policy.TimeoutErrorRetries` does not help: LiteLLM raises `APIConnectionError` there, which no retry policy field matches.
- `allowed_fails` and `cooldown_time` have no effect with one deployment per alias (see `router_utils/cooldown_handlers.py` in the image).
- `LITELLM_LOG=INFO` is what makes retries and fallbacks visible in the logs.
- Every alias has `input_cost_per_token` / `output_cost_per_token`: LiteLLM knows no price for Ollama models, and without one spend stays at $0 so budgets never trigger (ADR-014). A new alias needs a price too.

Client teams (`f1`, `mj`, `baux`) live in `config/tenants.yaml`: aliases allowed per team, budget per team, rpm/tpm limits per key. `scripts/bootstrap_tenants.py` applies the file through the LiteLLM admin API; it runs in the `tenants-bootstrap` one-shot service, which reuses the LiteLLM image. Things to keep in mind:

- The service sits in the `bootstrap` profile and runs with `docker compose run`, because `docker compose up --wait` fails on any container that exits, even with code 0, when no other service depends on it.
- Key values come from `.env` (`TEAM_KEY_*`) and are set with the `key` field of `/key/generate`, which makes re-runs converge instead of creating new keys. Keys have no model list: they inherit their team's.
- Existence is checked with `/team/list` and `/key/list?key_hash=<sha256 of the key>`, not `/team/info` or `/key/info`, which log a stack trace for every missing object.
- LiteLLM checks the budget before the rate limit, so a test of the rate limit must run on a team without a tight budget. Deleting a team deletes its keys.

Presidio notes:

- `presidio-analyzer` is built from `docker/presidio-analyzer/Dockerfile`: the official image plus `fr_core_news_lg`, installed as root with a pinned SHA-256 (the image runs as user 1001). Keep the base tag, the image tag in `compose.yaml` and the anonymizer tag on the same Presidio version.
- Its configuration is mounted from `config/presidio/` through `ANALYZER_CONF_FILE`, `NLP_CONF_FILE` and `RECOGNIZER_REGISTRY_CONF_FILE`. A language must be listed in all three files, and its spaCy model installed in the Dockerfile. Recognizers without `supported_languages` are created for every language of the registry.
- RAM measured at 1.6 GiB with the French and English models (1.0 GiB with French only), hence `mem_limit: 2g`.
- Both Presidio services set `GUNICORN_CMD_ARGS=--no-control-socket`: with the control socket on, gunicorn 25.1.0 forks the worker while a thread logs, and the worker can hang forever before `Booting worker` (gunicorn issue #3529). It happened in CI, not locally. Remove the flag only once the images ship a fixed gunicorn.
- The image's own healthcheck runs every 30 s; `compose.yaml` overrides it with a 5 s interval so `up --wait` does not stall.

Image versions are pinned in `compose.yaml`. When bumping them, keep the healthchecks working: the LiteLLM and Ollama images ship without curl or wget (the Presidio ones have curl), hence `python3` in the LiteLLM healthcheck and `ollama list` for Ollama. PostgreSQL 18 stores data under `/var/lib/postgresql/<major>/`, so the volume is mounted on the parent directory. `just` parses `.env` itself and needs quotes around values with spaces, such as `OLLAMA_MODELS`.

## Commands

Tasks run with [just](https://just.systems/) (`justfile`, which loads `.env`); there is no Makefile. Run `just` to list recipes.

- `just gateway-up`: start the stack, wait until every service is healthy, then create or update the client teams and keys. Creates `.env` from `.env.example` if missing.
- `just test`: run the pytest integration suite in `tests/` through `uv run` (dependencies in `pyproject.toml`, locked in `uv.lock`). Starts the stack if needed. Extra arguments go to pytest: `just test -k budget`, `just test tests/test_fallback.py`.
- `just smoke`: only `tests/test_routing.py`, a quick check that every alias answers after `just gateway-reload`.
- `just tenants`: apply `config/tenants.yaml` to the running gateway (also run by `just gateway-up`).
- `just gateway-reload`: restart LiteLLM after a change to `config/litellm.yaml`.
- `just gateway-down`: stop the stack; `just gateway-down --volumes` also deletes the database and the models.
- `just gateway-logs`: follow the logs.
- `just hooks`: install the pre-commit and commit-msg git hooks.
- `just lint`: run every pre-commit check (whitespace, YAML, yamllint, markdownlint, gitleaks) on all files.

CI (`.github/workflows/ci.yml`) runs pre-commit, a full-history gitleaks scan, the full stack and the pytest suite on a clean runner (about 3 minutes, limit 10), and checks that the PR title is a Conventional Commit, since PRs are squash-merged.

## Tests

`tests/` is an integration suite against the running stack; there are no unit tests, since the repo holds configuration and one bootstrap script. Keep in mind:

- `tests/helpers.py` loads `.env` and holds the shared helpers; `conftest.py` holds the fixtures. The session fixture runs `docker compose up --wait` and the bootstrap, both no-ops when everything already runs.
- Tests marked `disruptive` (stopping a container) are moved to the end of the run by `pytest_collection_modifyitems`: after `ollama-large` restarts, a pooled connection to the old server could make the next `chat-large` call wait for its timeout.
- Tests on limits and budgets use the `temp_team` fixture, never the real teams, so their spend and limits stay untouched. Clients have `max_retries=0`, otherwise the SDK retries a 429 and hides it.
- The job deliberately uses the production models and configuration: a test must fail when `config/litellm.yaml` is broken.

## Conventions

- Branch names come from Linear issues: `feature/lab-<n>-<slug>`.
- Commits follow Conventional Commits, enforced by a commit-msg hook.
- ADRs specific to this repo go in `docs/adr/`, copied from `000-template.md`. Cross-cutting ADRs live in `llmops-platform/docs/adr/`. ADR numbers are global to the portfolio and planned in Linear (001-006 and 010 cross-cutting, 007 LiteLLM, 008 ArgoCD, 009 KEDA, 012-013 F1, 014 here): take the next free number, never reuse one.
- Public repo: synthetic or public data only, never employer code or data. Claims come with real numbers (latency, detection rate, cost).
