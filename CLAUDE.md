# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

`llmops-gateway` is block 1 of a portfolio "internal AI platform": the single entry point to every LLM. LiteLLM Proxy handles per-team virtual keys, budgets, rate limiting and routing. A Presidio guardrail anonymizes French PII before inference and re-identifies the answer. Self-hosted Langfuse traces every call with its cost per team. Ollama serves models locally; vLLM replaces it once the gateway moves to Kubernetes in the sibling repo `llmops-platform`.

Planning lives in Linear (team key `LAB`, project "Plateforme IA · Gateway d'entreprise"). The cross-cutting vision document is "Portfolio IA — Vision, architecture et conventions".

## Current state

Milestones 1.1 and 1.2 (Presidio) are done; 1.3 (Langfuse) is in progress. `compose.yaml` runs LiteLLM Proxy (`litellm-database` image, which applies its Prisma migrations to PostgreSQL at startup), PostgreSQL and two Ollama servers sharing one model volume: `ollama` serves `chat-small` and `embed`, `ollama-large` serves `chat-large`, so stopping it simulates an outage of one model server. A one-shot `ollama-pull` service downloads every model in `OLLAMA_MODELS` before LiteLLM starts. Presidio Analyzer and Anonymizer run in the stack, called by the `pii-fr` guardrail of LiteLLM. Langfuse v4 runs from `compose.langfuse.yaml`, included by `compose.yaml` (see below); LiteLLM traces every call to it, to one project per team.

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
- Custom recognizers live in `docker/presidio-analyzer/pii_recognizers/` and are copied into the image. Presidio's registry finds a `type: predefined` recognizer by class name among the loaded subclasses of `EntityRecognizer`, so `server.py` imports the package before calling the stock `create_app()`, and the Dockerfile's `CMD` runs `server:create_app()`. A new recognizer needs its class exported in `__init__.py` and an entry in `config/presidio/recognizers.yaml`. `just gateway-up` and the test fixture pass `--build`, so code changes reach the image (the cached build takes about a second).
- The YAML loader silently drops constructor arguments it does not know, such as `PhoneRecognizer`'s `supported_regions`: set such arguments in a subclass (`FrPhoneRecognizer`), and check the result in a unit test.
- `global_regex_flags: 26` includes IGNORECASE for every pattern; `FrAddressRecognizer` uses `(?-i:...)` where a capital letter matters.
- Context words are matched as substrings of the lemmas of the 5 words before a match, so use single words or stems (`domicil`, `joign`), not phrases.
- A recognizer that is not a `PatternRecognizer` (`FrPersonRecognizer` subclasses `LocalRecognizer`) must give each result an `analysis_explanation` and the `recognition_metadata` name and identifier keys: the Analyzer's context enhancer uses both, and without the explanation `/analyze` answers 500 (`'NoneType' object has no attribute 'set_supportive_context_word'`). Unit tests call `analyze()` directly and do not catch it.
- `FrPersonRecognizer` reads `pii_recognizers/data/fr_first_names.txt`, built from INSEE's first names file by `scripts/build_first_names.py` (pinned URL and SHA-256). A first name alone scores 0.3, under the guardrail threshold, and only context words raise it.
- RAM measured at 1.6 GiB with the French and English models (1.0 GiB with French only), hence `mem_limit: 2g`.
- Both Presidio services set `GUNICORN_CMD_ARGS=--no-control-socket`: with the control socket on, gunicorn 25.1.0 forks the worker while a thread logs, and the worker can hang forever before `Booting worker` (gunicorn issue #3529). It happened in CI, not locally. Remove the flag only once the images ship a fixed gunicorn.
- The image's own healthcheck runs every 30 s; `compose.yaml` overrides it with a 5 s interval so `up --wait` does not stall.

PII guardrail notes (`guardrails:` in `config/litellm.yaml`):

- The class is `guardrails/presidio_markers.py`, a subclass of LiteLLM's Presidio guardrail that only overrides `_finalize_presidio_anonymize_numbered_tokens` (ADR-015: overlapping detections garbled the markers, and each message was numbered from 1). LiteLLM loads `module.Class` guardrails from the directory of its config file, hence the mount next to `/app/config.yaml`. It is a private method: after a LiteLLM bump, bump `litellm` in `pyproject.toml` to the same version and run `just test-unit`.
- With a custom class, LiteLLM passes every `litellm_params` key to the constructor, and `output_parse_pii` adds the post-call hook that unmasks the answer. The stock `guardrail: presidio` also creates an output masker unless `presidio_filter_scope: input`, which would mask the answer again.
- Per-team guardrails (`metadata.guardrails` on a team or key) are Enterprise-only (`_premium_user_check`, HTTP 403). The open-source path is `default_on: true` plus `opted_out_global_guardrails` in the team metadata, written by `scripts/bootstrap_tenants.py` from `pii_masking` in `config/tenants.yaml`. An opted-out team cannot trigger `pii-fr` from the request, hence the `pii-fr-on-request` twin with `default_on: false`.
- Presidio errors fail closed for masked teams (HTTP 500, nothing reaches the model).
- `mock_response` in the request body runs the guardrail without calling the model: the integration tests use it, and a marker in the mock answer comes back unmasked only if the prompt was masked with it. `POST /guardrails/apply_guardrail` (master key) shows the masked text.
- To see the exact prompt sent to Ollama, run LiteLLM with `LITELLM_LOG=DEBUG` and look for `POST Request Sent from LiteLLM`; Ollama 0.34.4 does not log prompts, even with `OLLAMA_DEBUG=2`.

Image versions are pinned in `compose.yaml`. When bumping them, keep the healthchecks working: the LiteLLM and Ollama images ship without curl or wget (the Presidio ones have curl), hence `python3` in the LiteLLM healthcheck and `ollama list` for Ollama. PostgreSQL 18 stores data under `/var/lib/postgresql/<major>/`, so the volume is mounted on the parent directory. `just` parses `.env` itself and needs quotes around values with spaces, such as `OLLAMA_MODELS`.

Langfuse (`compose.langfuse.yaml`), things to know:

- It is the official compose file, trimmed and pinned; its services are prefixed `langfuse-`, and it has its own PostgreSQL (reason in the README). `langfuse-web` and `langfuse-worker` share one environment through a YAML anchor: add an option there, not to one service only.
- `LANGFUSE_INIT_*` creates the organization, the project, its keys and the admin on first start only. Changing them in `.env` has no effect until `just gateway-down --volumes`.
- Next.js and the worker listen on the container's hostname, not on localhost, hence `$(hostname)` in their healthchecks.
- v4 only ingests over OTLP (`/api/public/otel/v1/traces`); `/api/public/ingestion` rejects traces, and `/api/public/traces/{id}` answers 404. Read traces back with `/api/public/v2/observations?traceId=`. In LiteLLM, use the `langfuse_otel` callback, not `langfuse`.
- S3 storage is SeaweedFS (`langfuse-s3`), not MinIO as in the official file: `weed server -s3` with the key pair in `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, which become its admin identity; the `langfuse` bucket is created on the first upload. `-ip.bind=0.0.0.0` is required, or the S3 API only listens on the container's IP and the healthcheck on 127.0.0.1 fails.
- Each team of `config/tenants.yaml` with a `langfuse` block gets its own organization, project, API keys and Viewer account, written by `scripts/bootstrap_langfuse.py` directly into Langfuse's PostgreSQL through LiteLLM's Prisma client (the equivalent APIs are Enterprise, ADR-016). It mirrors `web/src/initialize.ts` of the pinned Langfuse version: check its tables and hashes on any Langfuse upgrade. The same script creates the price of each alias in every project from `config/litellm.yaml`; its pattern also matches the model behind the alias (streamed calls and fallbacks carry that name), so two aliases may not serve the same model.
- A team's traces reach its project through the team's `logging` metadata in LiteLLM (set by `bootstrap_tenants.py`); calls without a team go to Gateway.
- `turn_off_message_logging: true` is global on purpose: `langfuse_otel` ignores the per-team and per-request switches in LiteLLM 1.83.14, and the guardrail restores real values in the answer before logging. To find a call's trace, send `metadata.generation_name` and filter `/api/public/v2/observations?name=`.

## Commands

Tasks run with [just](https://just.systems/) (`justfile`, which loads `.env`); there is no Makefile. Run `just` to list recipes.

- `just gateway-up`: start the stack, wait until every service is healthy, then create or update the client teams and keys. Creates `.env` from `.env.example` if missing.
- `just test`: run every pytest test in `tests/` through `uv run` (dependencies in `pyproject.toml`, locked in `uv.lock`). Starts the stack if needed. Extra arguments go to pytest: `just test -k budget`, `just test tests/integration/test_fallback.py`.
- `just test-unit`: only `tests/unit/`, the recognizer and guardrail class tests; no stack needed, about 2 seconds.
- `just gateway-bench`: start the stack, then benchmark the anonymization into `benchmarks/results.md` (about 30 minutes on CPU; `just gateway-bench --skip-llm` for Presidio and latency only, about 10 seconds).
- `just smoke`: only `tests/integration/test_routing.py`, a quick check that every alias answers after `just gateway-reload`.
- `just tenants`: apply `config/tenants.yaml` to the running gateway (also run by `just gateway-up`).
- `just gateway-reload`: restart LiteLLM after a change to `config/litellm.yaml`.
- `just gateway-down`: stop the stack; `just gateway-down --volumes` also deletes the databases, the Langfuse traces and the models.
- `just gateway-logs`: follow the logs.
- `just hooks`: install the pre-commit and commit-msg git hooks.
- `just lint`: run every pre-commit check (whitespace, YAML, yamllint, markdownlint, gitleaks) on all files.

CI (`.github/workflows/ci.yml`) runs pre-commit, a full-history gitleaks scan, the unit tests, the full stack and the pytest suite on a clean runner (about 3.5 minutes, limit 10), and checks that the PR title is a Conventional Commit, since PRs are squash-merged.

## Benchmark

`benchmarks/generate_dataset.py` writes `benchmarks/dataset.jsonl` (100 French texts, fixed seed, committed); `tests/unit/test_dataset.py` checks that it still matches the generator, that annotations point at their values and that identifiers have valid check digits. Faker's relative dates (`-3y`, `date_of_birth`) depend on the current day, so the generator uses fixed bounds: keep it that way, or the file changes every day.

`benchmarks/run_bench.py` reads the entities and threshold of `pii-fr` from `config/litellm.yaml`, runs Presidio as the guardrail does (with `merge_overlaps` from `guardrails/presidio_markers.py`), asks each Ollama model for the same entities in JSON, and measures the gateway with and without the guardrail on `mock_response`. It queries Ollama directly on `OLLAMA_PORT` (11435, since a local Ollama install usually holds 11434) and pulls `qwen2.5:7b` into the model volume on first run; that model is not in `OLLAMA_MODELS`. `results.md` is generated: rerun, never edit. Avoid other heavy work while it runs, it skews the latencies.

When changing a recognizer because of the benchmark, also measure on a held-out set, or the rules end up tuned to `dataset.jsonl`: `uv run python benchmarks/generate_dataset.py --seed 2026 --output /tmp/heldout.jsonl`, then `uv run python benchmarks/run_bench.py --skip-llm --dataset /tmp/heldout.jsonl --results /tmp/heldout.md`. Both sets come from the same templates, so this checks new values, not new kinds of text.

## Tests

`tests/unit/` tests the Presidio recognizers and the guardrail class without Docker: its conftest builds the registry from the real `config/presidio/recognizers.yaml` with the `presidio-analyzer` package, pinned to the image's version (as are `phonenumbers` and `litellm`), and `pytest.ini_options.pythonpath` makes `pii_recognizers` and `presidio_markers` importable. Each recognizer has at least 10 valid cases plus false positives and edge cases; valid NIRs, tax numbers and IBANs were generated and checked with python-stdnum (`uvx --with python-stdnum python`).

`tests/integration/` runs against the stack. Keep in mind:

- `tests/integration/helpers.py` loads `.env` and holds the shared helpers; `conftest.py` holds the fixtures. The session fixture runs `docker compose up --wait` and the bootstrap, both no-ops when everything already runs.
- Tests marked `disruptive` (stopping a container, or restarting LiteLLM at `DEBUG` with `tests/integration/compose.litellm-debug.yaml` in `test_no_leak.py`) are moved to the end of the run by `pytest_collection_modifyitems`: after `ollama-large` restarts, a pooled connection to the old server could make the next `chat-large` call wait for its timeout.
- Tests on limits and budgets use the `temp_team` fixture, never the real teams, so their spend and limits stay untouched. Clients have `max_retries=0`, otherwise the SDK retries a 429 and hides it.
- `test_no_leak.py` lists the words Presidio leaves in clear on `benchmarks/dataset.jsonl` (`KNOWN_MISSES`). A recognizer change that masks one of them, or misses a new one, must update that list, and rerun `just gateway-bench` so `benchmarks/results.md` agrees. The conftest's session fixture runs `docker compose up`, which undoes any container-level change made before `pytest` starts: to prove a test catches a broken setting, change the file itself.
- The job deliberately uses the production models and configuration: a test must fail when `config/litellm.yaml` is broken.

## Conventions

- Branch names come from Linear issues: `feature/lab-<n>-<slug>`.
- Commits follow Conventional Commits, enforced by a commit-msg hook.
- ADRs specific to this repo go in `docs/adr/`, copied from `000-template.md`. Cross-cutting ADRs live in `llmops-platform/docs/adr/`. ADR numbers are global to the portfolio and planned in Linear (001-006 and 010 cross-cutting, 007 LiteLLM, 008 ArgoCD, 009 KEDA, 012-013 F1, 014 here): take the next free number, never reuse one.
- Public repo: synthetic or public data only, never employer code or data. Claims come with real numbers (latency, detection rate, cost).
