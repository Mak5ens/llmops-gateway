# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

`llmops-gateway` is block 1 of a portfolio "internal AI platform": the single entry point to every LLM. LiteLLM Proxy handles per-team virtual keys, budgets, rate limiting and routing. A Presidio pre-call hook anonymizes French PII before inference and re-identifies the answer. Self-hosted Langfuse traces every call with its cost per team. Ollama serves models locally; vLLM replaces it once the gateway moves to Kubernetes in the sibling repo `llmops-platform`.

Planning lives in Linear (team key `LAB`, project "Plateforme IA · Gateway d'entreprise"). The cross-cutting vision document is "Portfolio IA — Vision, architecture et conventions".

## Current state

There is no application code yet, only the repo scaffold. `make up`, `make down` and `make test` deliberately fail with a pointer to LAB-109 (Docker Compose: LiteLLM, PostgreSQL, Ollama). Replace them when the stack lands, and update this file with the real commands.

## Commands

- `make hooks`: install the pre-commit and commit-msg git hooks.
- `make lint`: run every pre-commit check (whitespace, YAML, yamllint, markdownlint, gitleaks) on all files.
- Locally, the markdownlint hook needs Node, which needs `libatomic1` on this WSL machine. Workaround: `SKIP=markdownlint-cli2 pre-commit run --all-files`.

CI (`.github/workflows/ci.yml`) runs pre-commit, a full-history gitleaks scan, and checks that the PR title is a Conventional Commit, since PRs are squash-merged.

## Conventions

- Branch names come from Linear issues: `feature/lab-<n>-<slug>`.
- Commits follow Conventional Commits, enforced by a commit-msg hook.
- ADRs specific to this repo go in `docs/adr/`, copied from `000-template.md`. Cross-cutting ADRs live in `llmops-platform/docs/adr/`.
- Public repo: synthetic or public data only, never employer code or data. Claims come with real numbers (latency, detection rate, cost).
