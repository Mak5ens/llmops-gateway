# Architecture decision records

One short record per structuring choice: context, options compared, decision, consequences. Start from [`000-template.md`](000-template.md) and name the file `NNN-short-title.md`.

This folder only holds decisions specific to this repo. Cross-cutting decisions live in [`llmops-platform/docs/adr/`](https://github.com/Mak5ens/llmops-platform/tree/main/docs/adr).

ADR numbers are global to the portfolio, so the numbers here are not consecutive.

| ADR | Decision | Status |
| -- | -- | -- |
| [ADR-007](007-litellm-as-llm-gateway.md) | LiteLLM Proxy as the LLM gateway, rather than our own, Envoy AI Gateway, Kong or a SaaS | Accepted |
| [ADR-014](014-internal-price-for-self-hosted-models.md) | Budget self-hosted models with an internal price per token | Accepted |
| [ADR-015](015-presidio-marker-fixes.md) | Fix the numbered markers of LiteLLM's Presidio guardrail in a subclass | Accepted |
| [ADR-016](016-langfuse-project-per-team.md) | One Langfuse organization per team, provisioned in Langfuse's database | Accepted |
