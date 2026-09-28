# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

`llmops-gateway` is block 1 of a portfolio "internal AI platform": the single entry point to every LLM. LiteLLM Proxy handles per-team virtual keys, budgets, rate limiting and routing. A Presidio pre-call hook anonymizes French PII before inference and re-identifies the answer. Self-hosted Langfuse traces every call with its cost per team. Ollama serves models locally; vLLM replaces it once the gateway moves to Kubernetes in the sibling repo `llmops-platform`.

Planning lives in Linear (team key `LAB`, project "Plateforme IA · Gateway d'entreprise"). The cross-cutting vision document is "Portfolio IA — Vision, architecture et conventions".

## Current state

Milestone 1.1 is in progress. `compose.yaml` runs LiteLLM Proxy (`litellm-database` image, which applies its Prisma migrations to PostgreSQL at startup), PostgreSQL and Ollama. A one-shot `ollama-pull` service downloads `OLLAMA_MODEL` before LiteLLM starts. Models exposed by the gateway are declared in `config/litellm.yaml`; callers use aliases such as `local-chat`, never the underlying model name. Presidio (LAB-113) and Langfuse (LAB-117) are not in the stack yet.

Image versions are pinned in `compose.yaml`. When bumping them, keep the healthchecks working: the images ship without curl or wget, hence `python3` in the LiteLLM healthcheck and `ollama list` for Ollama. PostgreSQL 18 stores data under `/var/lib/postgresql/<major>/`, so the volume is mounted on the parent directory.

## Commands

Tasks run with [just](https://just.systems/) (`justfile`, which loads `.env`); there is no Makefile. Run `just` to list recipes.

- `just gateway-up`: start the stack and wait until every service is healthy. Creates `.env` from `.env.example` if missing.
- `just smoke` (alias `just test`): call the gateway with the OpenAI SDK through `uv run`, and fail on an empty answer.
- `just gateway-down`: stop the stack; `just gateway-down --volumes` also deletes the database and the models.
- `just gateway-logs`: follow the logs.
- `just hooks`: install the pre-commit and commit-msg git hooks.
- `just lint`: run every pre-commit check (whitespace, YAML, yamllint, markdownlint, gitleaks) on all files.

CI (`.github/workflows/ci.yml`) runs pre-commit, a full-history gitleaks scan, the full stack with the smoke test on a clean runner, and checks that the PR title is a Conventional Commit, since PRs are squash-merged.

## Conventions

- Branch names come from Linear issues: `feature/lab-<n>-<slug>`.
- Commits follow Conventional Commits, enforced by a commit-msg hook.
- ADRs specific to this repo go in `docs/adr/`, copied from `000-template.md`. Cross-cutting ADRs live in `llmops-platform/docs/adr/`.
- Public repo: synthetic or public data only, never employer code or data. Claims come with real numbers (latency, detection rate, cost).
