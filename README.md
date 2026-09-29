# llmops-gateway

[![CI](https://github.com/Mak5ens/llmops-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/Mak5ens/llmops-gateway/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**One gateway for every LLM call in the company: per-team keys and budgets, French PII anonymized before inference, every call traced and priced.**

> Status: under construction. Milestone 1.1 (local gateway) is done: LiteLLM, PostgreSQL and Ollama run with Docker Compose, behind usage aliases with a fallback, and three client teams have their own key, budget and rate limit. Milestone 1.2 (Presidio anonymization) is in progress: Presidio runs in the stack with a French model, and is not wired into the gateway yet. See the [roadmap](#roadmap).

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

Requires Docker with Compose v2, [just](https://just.systems/), and [uv](https://docs.astral.sh/uv/) for the tests.

```bash
just gateway-up       # LiteLLM, PostgreSQL, two Ollama servers, Presidio, then the client teams; creates .env on first run
just test             # integration tests: aliases, access per team, rate limit, budget, fallback, Presidio
just gateway-down     # add --volumes to also delete the database and the downloaded models
```

First start on a clean machine: about 2 minutes 10 seconds, including the download of three models (about 2 GB) and the build of the Presidio Analyzer image with its French model (2.8 GB on disk).
The gateway listens on `http://localhost:4000` and speaks the OpenAI API. Call it with a team key from `.env`, such as `TEAM_KEY_F1`:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:4000", api_key="sk-local-dev-team-f1")
client.chat.completions.create(model="chat-small", messages=[{"role": "user", "content": "Hello"}])
client.embeddings.create(model="embed", input="Le locataire a payé son loyer en retard.")
```

Langfuse joins the stack in milestone 1.3. To contribute, install the git hooks (requires [pre-commit](https://pre-commit.com/)) with `just hooks`, and run `just lint`. Run `just` alone to list every recipe.

## Models and routing

Teams call **usage aliases**, never model names. The platform decides which model serves each alias in [`config/litellm.yaml`](config/litellm.yaml), so a model can be swapped without touching any client.

| Alias | Use | Model today | Server | Timeout |
| -- | -- | -- | -- | -- |
| `chat-small` | Short answers, classification, extraction | `qwen2.5:0.5b` | `ollama` | 30 s |
| `chat-large` | Better answers, slower | `qwen2.5:1.5b` | `ollama-large` | 20 s, then fallback to `chat-small` |
| `embed` | Embeddings, multilingual (French included), 768 dimensions | `granite-embedding:278m` | `ollama` | 30 s |

**Fallback.** If `chat-large` fails or times out, the gateway answers with `chat-small`. The response header `x-litellm-model-group` says which alias actually served the call, and the logs show `Falling back to model_group = chat-small`.
Measured with `just test -k fallback` on a laptop CPU:

| Situation | Time to answer through `chat-small` |
| -- | -- |
| Server dies while the gateway holds an open connection to it (worst case) | 21 s: the full `chat-large` timeout, then the fallback |
| Following calls during the outage | about 3 s: the connection fails at once |
| Server back | `chat-large` serves again on the next call |

`chat-large` has no retry (`num_retries: 0`): the fallback is its retry. With one retry, the worst case measured 44 s, since each attempt waits for the full timeout. The other aliases keep one retry.

### Swap or add a model

1. Add the model to `OLLAMA_MODELS` in `.env` (and in `.env.example` for everyone), then run `just gateway-up` to download it.
2. In `config/litellm.yaml`, point an alias to it, or add a new entry to `model_list` with a usage alias as `model_name`, the model as `ollama_chat/<name>` (or `ollama/<name>` for embeddings), the server as `api_base`, and a `timeout`.
3. Run `just gateway-reload`: Compose does not see changes to a mounted file, so LiteLLM must restart to read it.
4. Run `just smoke` (the alias tests), and add the new alias to `tests/test_routing.py` if you created one.

Clients keep calling the same alias throughout.

## Teams, keys and budgets

Every client team has its own virtual key, the aliases it may call, a monthly budget and a rate limit, declared in [`config/tenants.yaml`](config/tenants.yaml).
The master key stays with the platform team: it creates teams and keys, and no application uses it.

| Team | Tenant | Aliases | Budget | Key limits |
| -- | -- | -- | -- | -- |
| `f1` | F1 strategy analyst (agent with RAG) | `chat-small`, `chat-large`, `embed` | $10 / 30 days | 60 requests and 100k tokens per minute |
| `mj` | Game master assistant | `chat-small`, `chat-large` | $5 / 30 days | 30 requests and 50k tokens per minute |
| `baux` | Lease compliance checker | `chat-large`, `embed` | $5 / 30 days | 20 requests and 50k tokens per minute |

`just gateway-up` applies the file through [`scripts/bootstrap_tenants.py`](scripts/bootstrap_tenants.py), and `just tenants` applies it again after an edit, without restarting anything.
The script is idempotent: it creates what is missing, updates what exists, and never deletes a team.
Key values come from `.env` (`TEAM_KEY_F1`, `TEAM_KEY_MJ`, `TEAM_KEY_BAUX`); on the cluster they will come from a secret manager.

A team that steps out of its limits gets an explicit error, and only that team is blocked:

| Situation | Answer |
| -- | -- |
| Alias not allowed for the team | `401 team_model_access_denied`: *This team can only access models=['chat-small', 'chat-large']. Tried to access embed* |
| More requests or tokens per minute than the key allows | `429`: *Rate limit exceeded [...] Current limit: 2, Remaining: 0. Limit resets at: [time]* |
| Budget spent | `400 budget_exceeded`: *Budget has been exceeded! Team=[team] Current cost: [...], Max budget: [...]* |

`tests/test_tenants.py` checks all three on a throwaway team, checks that `f1` still answers meanwhile, and checks that re-running the bootstrap left exactly one key per team.
The budget blocks the call right after the one that crossed it: LiteLLM counts spend in memory at once, and writes it to PostgreSQL in batches, so `/team/info` may show it a few seconds later.

**Why local models have a price.** LiteLLM knows no price for Ollama models, so spend stayed at $0 and budgets never triggered. Each alias carries an internal price per token instead (`chat-small` $0.10 / $0.40 per million tokens in / out, `chat-large` five times more, `embed` $0.02), a chargeback rate that works the same once a paid API joins. See [ADR-014](docs/adr/014-internal-price-for-self-hosted-models.md).

## Personal data detection (Presidio)

[Presidio](https://microsoft.github.io/presidio/) runs as two services. The **Analyzer** finds personal data in a text and returns its type, position and score; the **Anonymizer** replaces those spans with placeholders.
The gateway does not call them yet: LAB-115 turns them into a LiteLLM guardrail. Until then, they can be called directly on `127.0.0.1`:

```bash
curl -s localhost:5002/analyze -H 'content-type: application/json' \
  -d '{"text": "Je suis Marie Dupont et j'"'"'habite à Lyon.", "language": "fr"}'
# PERSON "Marie Dupont" and LOCATION "Lyon", score 0.85 each
```

The official Analyzer image only ships an English spaCy model, which misses French names and places. [`docker/presidio-analyzer/Dockerfile`](docker/presidio-analyzer/Dockerfile) adds `fr_core_news_lg` 3.8.0, pinned by version and SHA-256.
The configuration is mounted from [`config/presidio/`](config/presidio/), so changing it needs `docker compose restart presidio-analyzer`, not a rebuild:

| File | Sets |
| -- | -- |
| `nlp.yaml` | One spaCy model per language (`fr`, `en`) and how their labels map to Presidio entities |
| `recognizers.yaml` | The pattern recognizers (email, IBAN, phone, credit card, IP, URL, date) and the spaCy NER recognizer; French identifiers come in LAB-114 |
| `analyzer.yaml` | Supported languages and the default score threshold |

Memory of the Analyzer, measured with `docker stats` after 30 requests:

| Models loaded | RAM |
| -- | -- |
| `en_core_web_lg` (official image) | 740 MiB |
| `fr_core_news_lg` | 1.0 GiB |
| `fr_core_news_lg` + `en_core_web_lg` (this stack) | 1.6 GiB |

English costs 570 MiB more; it stays so that prompts in English, such as F1 data, are still analyzed. The container is limited to 2 GiB.
It starts in about 6 seconds once the image is built, and analyzes a 30-word French sentence in about 6 ms on a laptop CPU.

## Tests

Every promise of the gateway is an integration test in [`tests/`](tests/): pytest calls the real stack with the OpenAI SDK and a team key, as a client team would.

| File | Checks |
| -- | -- |
| `test_routing.py` | Each alias answers, served by its own model (header `x-litellm-model-group`); `embed` returns 768 dimensions |
| `test_tenants.py` | Allowed and refused aliases per team (401), rate limit (429), budget (400), isolation from other teams, idempotent bootstrap |
| `test_presidio.py` | The Analyzer finds a person, a place and an email in French, and still works in English; the Anonymizer replaces what it found |
| `test_fallback.py` | With `ollama-large` stopped, `chat-large` is served by `chat-small` within 30 s and the logs show the fallback |

`just test` starts the stack if it is not running, and passes its arguments to pytest: `just test -k budget`, `just test tests/test_fallback.py`.
The fallback test stops a container, so it always runs last, and restarts it afterwards even on failure.

CI runs the suite on every PR on a clean runner, with the same models as in development: 3 min 22 s for the job, of which 2 min 21 s to start the stack, download the models and build the Presidio Analyzer image. A tiny model in CI was not worth it: it would need a CI-only LiteLLM configuration, and the tests would no longer check the real one.
Removing the fallback from `config/litellm.yaml` makes `test_fallback.py` fail with a `500 APIConnectionError`, so a broken routing configuration cannot be merged.

## Roadmap

- [x] **1.1 Local gateway**: LiteLLM + Ollama + PostgreSQL in Docker Compose, at least two models, per-team virtual keys, budgets and rate limiting.
- [ ] **1.2 Presidio anonymization** (Presidio with a French model in the stack; French recognizers next): pre-call hook, French recognizers, re-identification. Benchmark of added latency and detection rate on 100 texts.
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
