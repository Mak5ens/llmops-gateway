# ADR-007: LiteLLM Proxy as the LLM gateway

- **Status:** Accepted
- **Date:** 2026-10-01

## Context

Every call to a model goes through one gateway. It must issue a key per team, enforce budgets in euros and rate limits, fall back from one model to another, mask French personal data before inference and put it back into the answer, and send each call's cost to Langfuse. It must run the same on a laptop (Docker Compose, Ollama) and on the cluster (vLLM), with self-hosted models only: no prompt leaves the platform.

The HTTP gateway is a separate concern (ADR-005): Envoy Gateway terminates TLS and routes host names into the cluster. The LLM gateway sits behind it and handles what is specific to models.

## Options considered

| Option | Pros | Cons |
| -- | -- | -- |
| A. Our own gateway (FastAPI) | Exactly what we need, no unused feature, no vendor | Keys, budgets, cost per token, fallback, streaming, unmasking in streams and tracing to rebuild and maintain: months of work, for a tool that is not the point of the platform |
| B. LiteLLM Proxy | Keys, team budgets, rpm/tpm limits, fallback, Presidio guardrail, Langfuse callback and admin API, all open source; OpenAI-compatible API; about 60,000 GitHub stars; MIT outside `enterprise/` | Per-team guardrails, SSO beyond 5 users and audit logs are Enterprise; a fast-moving codebase with open bugs on the features we use; Python and a PostgreSQL to run |
| C. Envoy AI Gateway, renamed Agent Router (Apache 2.0) | Runs on Envoy Gateway, already in the cluster; token quotas and usage-based rate limits; v1.0 on June 23, 2026 | No keys issued per team, no budget in currency, no PII guardrail; Kubernetes only, so no Compose setup for development; about 2,200 stars |
| D. API gateway with AI plugins: Kong | Mature API gateway | The open-source AI proxy targets one provider; token rate limiting, load balancing and the PII sanitizer need an Enterprise licence |
| E. SaaS gateway (Portkey, OpenRouter, Cloudflare AI Gateway) | Nothing to run | Prompts leave the platform, before masking, which defeats the GDPR goal of block 1; self-hosted models reachable only from outside; Portkey was bought by Palo Alto Networks (closed May 29, 2026), its roadmap now follows a security vendor |

## Decision

We choose **B**, LiteLLM Proxy, in the `litellm-database` image pinned to `main-v1.83.14-stable`. It is the only option that covers keys, budgets, fallback, PII masking and tracing without a licence, and runs the same in Compose and on Kubernetes. Our code around it stays small: `config/litellm.yaml` (107 lines), `config/tenants.yaml` (74 lines), two bootstrap scripts and one 85-line guardrail subclass.

## Consequences

Limits met while building block 1, each with its workaround and a test that guards it:

- **Enterprise gates.** Per-team guardrails answer 403: the guardrail is on by default and teams opt out in their metadata (`pii_masking` in `config/tenants.yaml`).
- **Bugs in the Presidio guardrail.** Overlapping detections garbled the prompt, and each message was numbered from 1 (BerriAI/litellm#42130 and #31959, open): fixed in a subclass of a private method (ADR-015), checked by unit tests against the pinned version.
- **Switches ignored.** `langfuse_otel` ignores the per-team and per-request message logging switches, so messages are never traced, for every team (ADR-016). `langfuse_otel` sends no cost either: Langfuse computes it from prices our bootstrap writes.
- **Retries.** A connection error is not matched by any retry policy field, and a pooled connection to a dead server waits for the full timeout: the timeout is the worst-case failover time, and `chat-large` does not retry.
- **Supply chain.** On March 24, 2026, LiteLLM 1.82.7 and 1.82.8 on PyPI carried a credential stealer for a few hours. Image and Python package are pinned to the same version, and upgrades are deliberate, tested changes.

What we accept: a dependency on one company's open-source project, whose Enterprise line may grow. Each LiteLLM upgrade runs the full suite before it is merged.

Exit plan: clients only see the OpenAI API, Presidio runs as its own services, and traces go to Langfuse over OpenTelemetry, so none of them depends on LiteLLM. Leaving would mean rebuilding keys and budgets, either in our own service or on Agent Router once it manages them. We revisit this if a feature we use moves to Enterprise, if a security fix is not released within days, or if Agent Router gains per-team keys and budgets.
