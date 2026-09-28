# llmops-gateway

[![CI](https://github.com/Mak5ens/llmops-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/Mak5ens/llmops-gateway/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**One gateway for every LLM call in the company: per-team keys and budgets, French PII anonymized before inference, every call traced and priced.**

> Status: under construction. Milestone 1.1 (local gateway) is in progress. See the [roadmap](#roadmap).

## Why

In the (fictional) 200-person company behind this project, every team calls LLMs its own way: shared API keys, no cost tracking, personal data sent in clear text.
The Platform team puts a **single gateway** in front of every model. Product teams become tenants: each one gets its own virtual key, budget and traces.

This repo is block 1 of an [internal AI platform portfolio](#part-of-an-internal-ai-platform). It runs with Docker Compose before any cluster exists, then moves to Kubernetes in [`llmops-platform`](https://github.com/Mak5ens/llmops-platform).

## How it works

```mermaid
flowchart LR
    app["Team app<br/>(virtual key)"] --> litellm["LiteLLM Proxy<br/>auth · budget · rate limit · routing"]
    litellm -- "pre-call hook" --> presidio["Presidio<br/>French recognizers"]
    presidio -- "anonymized prompt" --> litellm
    litellm --> model["Ollama (dev)<br/>vLLM (cluster)"]
    model --> litellm
    litellm -- "re-identified answer" --> app
    litellm -.-> pg[("PostgreSQL<br/>keys · spend")]
    litellm -. "trace: tokens, latency, cost per team" .-> langfuse["Langfuse<br/>self-hosted"]
```

1. A team calls one URL with its **virtual key**. LiteLLM checks the key, the budget and the rate limit, then routes by model and use case (`/chat`, `/embed`, `/ocr`), with fallback between models.
2. A **Presidio** pre-call hook replaces personal data (names, addresses, IBAN, French tax number, phone numbers) with placeholders. The model only sees the anonymized prompt.
3. The answer is **re-identified** before it goes back to the caller.
4. Every call is traced in a **self-hosted Langfuse** with latency, tokens and cost per team. No trace leaves the company, and an automated test checks that traces contain no personal data.

## Stack

| Function | Tool |
| -- | -- |
| LLM gateway | [LiteLLM Proxy](https://docs.litellm.ai/docs/simple_proxy) |
| PII anonymization | [Microsoft Presidio](https://microsoft.github.io/presidio/) with French recognizers |
| Tracing and cost | [Langfuse](https://langfuse.com/) self-hosted (PostgreSQL, ClickHouse, Redis, MinIO) |
| Local models | [Ollama](https://ollama.com/) with a small open-source model; vLLM takes over on the cluster |
| Gateway database | PostgreSQL |

## Quick start

Not runnable yet: the Docker Compose stack is being built in milestone 1.1. The target is a single command:

```bash
make up     # docker compose up: LiteLLM, PostgreSQL, Ollama, Presidio, Langfuse
make test   # gateway, anonymization and "no PII in traces" tests
make down
```

To contribute today, install the git hooks (requires [pre-commit](https://pre-commit.com/)):

```bash
make hooks
make lint
```

## Roadmap

- [ ] **1.1 Local gateway**: LiteLLM + Ollama + PostgreSQL in Docker Compose, at least two models, per-team virtual keys, budgets and rate limiting.
- [ ] **1.2 Presidio anonymization**: pre-call hook, French recognizers, re-identification. Benchmark of added latency and detection rate on 100 texts.
- [ ] **1.3 Tracing and cost with Langfuse**: self-hosted Langfuse, cost per team, automated test proving traces hold no personal data.
- [ ] **1.4 ADR, README and article 1**: why LiteLLM rather than a home-made or cloud gateway; demo GIF.

Definition of done: a text with a name, an IBAN and an address goes in, the model only receives the anonymized version, and the answer comes back re-identified.

## Architecture decisions

Repo-specific ADRs live in [`docs/adr/`](docs/adr/). Cross-cutting decisions (cloud, CI, Langfuse self-hosted, multi-repo layout) live in [`llmops-platform/docs/adr/`](https://github.com/Mak5ens/llmops-platform/tree/main/docs/adr).

## Part of an internal AI platform

| Repo | Role |
| -- | -- |
| **llmops-gateway** (this repo) | Block 1: single entry point to LLMs, keys, budgets, anonymization, tracing |
| [llmops-platform](https://github.com/Mak5ens/llmops-platform) | Block 2: Kubernetes in GitOps, vLLM autoscaling, GPU observability, costs |
| [f1-strategy-analyst](https://github.com/Mak5ens/f1-strategy-analyst) | Block 3: first tenant, an agent with RAG and an evaluation CI |

Write-up: article 1, *Anonymiser avant d'inférer : une gateway LLM conforme au RGPD*, coming on [maxence-labbe.fr](https://maxence-labbe.fr).

## License

[MIT](LICENSE). Synthetic or public data only; no employer code or data.
