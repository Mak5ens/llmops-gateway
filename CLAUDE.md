# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

`llmops-gateway` is block 1 of a portfolio "internal AI platform": the single entry point to every LLM. LiteLLM Proxy handles per-team virtual keys, budgets, rate limiting and routing. A Presidio pre-call hook anonymizes French PII before inference and re-identifies the answer. Self-hosted Langfuse traces every call with its cost per team. Ollama serves models locally; vLLM replaces it once the gateway moves to Kubernetes in the sibling repo `llmops-platform`.

Planning lives in Linear (team key `LAB`, project "Plateforme IA · Gateway d'entreprise"). The cross-cutting vision document is "Portfolio IA — Vision, architecture et conventions".

## Current state

Milestone 1.1 is in progress. `compose.yaml` runs LiteLLM Proxy (`litellm-database` image, which applies its Prisma migrations to PostgreSQL at startup), PostgreSQL and two Ollama servers sharing one model volume: `ollama` serves `chat-small` and `embed`, `ollama-large` serves `chat-large`, so stopping it simulates an outage of one model server. A one-shot `ollama-pull` service downloads every model in `OLLAMA_MODELS` before LiteLLM starts. Presidio (LAB-113) and Langfuse (LAB-117) are not in the stack yet.

Routing lives in `config/litellm.yaml`: callers only use usage aliases (`chat-small`, `chat-large`, `embed`), and `chat-large` falls back to `chat-small`. Things learned the hard way, keep them in mind when touching it:

- LiteLLM reads the file only at startup: run `just gateway-reload` after editing it, or the old model list stays loaded.
- A pooled connection to a server that died hangs until the model `timeout`, so that timeout is the worst-case failover time. `chat-large` has `num_retries: 0` because each retry waits the full timeout again. `retry_policy.TimeoutErrorRetries` does not help: LiteLLM raises `APIConnectionError` there, which no retry policy field matches.
- `allowed_fails` and `cooldown_time` have no effect with one deployment per alias (see `router_utils/cooldown_handlers.py` in the image).
- `LITELLM_LOG=INFO` is what makes retries and fallbacks visible in the logs.
- Every alias has `input_cost_per_token` / `output_cost_per_token`: LiteLLM knows no price for Ollama models, and without one spend stays at $0 so budgets never trigger (ADR-001). A new alias needs a price too.

Client teams (`f1`, `mj`, `baux`) live in `config/tenants.yaml`: aliases allowed per team, budget per team, rpm/tpm limits per key. `scripts/bootstrap_tenants.py` applies the file through the LiteLLM admin API; it runs in the `tenants-bootstrap` one-shot service, which reuses the LiteLLM image. Things to keep in mind:

- The service sits in the `bootstrap` profile and runs with `docker compose run`, because `docker compose up --wait` fails on any container that exits, even with code 0, when no other service depends on it.
- Key values come from `.env` (`TEAM_KEY_*`) and are set with the `key` field of `/key/generate`, which makes re-runs converge instead of creating new keys. Keys have no model list: they inherit their team's.
- Existence is checked with `/team/list` and `/key/list?key_hash=<sha256 of the key>`, not `/team/info` or `/key/info`, which log a stack trace for every missing object.
- LiteLLM checks the budget before the rate limit, so a test of the rate limit must run on a team without a tight budget. Deleting a team deletes its keys.

Image versions are pinned in `compose.yaml`. When bumping them, keep the healthchecks working: the images ship without curl or wget, hence `python3` in the LiteLLM healthcheck and `ollama list` for Ollama. PostgreSQL 18 stores data under `/var/lib/postgresql/<major>/`, so the volume is mounted on the parent directory. `just` parses `.env` itself and needs quotes around values with spaces, such as `OLLAMA_MODELS`.

## Commands

Tasks run with [just](https://just.systems/) (`justfile`, which loads `.env`); there is no Makefile. Run `just` to list recipes.

- `just gateway-up`: start the stack, wait until every service is healthy, then create or update the client teams and keys. Creates `.env` from `.env.example` if missing.
- `just smoke`: call every alias with the OpenAI SDK through `uv run`, and fail on an empty answer.
- `just fallback-test`: warm a connection to `chat-large`, stop `ollama-large`, and check `chat-small` answers within 30 s; restarts `ollama-large` even on failure.
- `just tenants`: apply `config/tenants.yaml` to the running gateway (also run by `just gateway-up`).
- `just tenants-test`: re-run the bootstrap, then check allowed and refused aliases per team, the rate limit (429) and the budget (400) on a throwaway team, isolation from `f1`, and one key per team.
- `just test`: smoke, tenants-test and fallback-test.
- `just gateway-reload`: restart LiteLLM after a change to `config/litellm.yaml`.
- `just gateway-down`: stop the stack; `just gateway-down --volumes` also deletes the database and the models.
- `just gateway-logs`: follow the logs.
- `just hooks`: install the pre-commit and commit-msg git hooks.
- `just lint`: run every pre-commit check (whitespace, YAML, yamllint, markdownlint, gitleaks) on all files.

CI (`.github/workflows/ci.yml`) runs pre-commit, a full-history gitleaks scan, the full stack with the smoke, tenant and fallback tests on a clean runner, and checks that the PR title is a Conventional Commit, since PRs are squash-merged.

## Conventions

- Branch names come from Linear issues: `feature/lab-<n>-<slug>`.
- Commits follow Conventional Commits, enforced by a commit-msg hook.
- ADRs specific to this repo go in `docs/adr/`, copied from `000-template.md`. Cross-cutting ADRs live in `llmops-platform/docs/adr/`.
- Public repo: synthetic or public data only, never employer code or data. Claims come with real numbers (latency, detection rate, cost).
