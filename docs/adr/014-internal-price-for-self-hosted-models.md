# ADR-014: Budget self-hosted models with an internal price per token

- **Status:** Accepted
- **Date:** 2026-09-29

## Context

Each client team gets a budget in dollars (LAB-111). LiteLLM counts spend from a price per token, and it knows no price for Ollama models: measured on LiteLLM 1.83.14, a team with a budget of $0.000001 kept its spend at $0 and was never blocked.
Self-hosted inference is not free, though: GPU nodes, energy and the platform team's time are real costs that the company wants to share out between teams.
On the cluster, vLLM will serve the same aliases, and a team may later be routed to a paid API behind the same alias.

## Options considered

| Option | Pros | Cons |
| -- | -- | -- |
| A. Internal price per token on each alias (`input_cost_per_token`, `output_cost_per_token` in `config/litellm.yaml`) | Budgets work unchanged; one unit (dollars) for local and paid models; spend per team is ready for Langfuse (1.3) | The price is a convention, to be reviewed when GPU costs are known |
| B. Only token limits (`tpm_limit`), no dollar budget | No invented price | No monthly envelope per team; no single unit once a paid API joins; spend reports show $0 |
| C. Price computed from GPU hours | Closest to the real cost | Needs cluster metrics that do not exist yet (block 2) |

## Decision

We choose **A**: every alias carries an internal price close to hosted models of the same class, and chat-large costs five times chat-small, per token.

| Alias | Input, $ per million tokens | Output, $ per million tokens |
| -- | -- | -- |
| `chat-small` | 0.10 | 0.40 |
| `chat-large` | 0.50 | 2.00 |
| `embed` | 0.02 | none |

The price is a chargeback rate, not a bill: it tells a team what its usage would cost, and lets the platform stop a team that goes out of control.

## Consequences

- Dollar budgets, per-team spend and later Langfuse cost reports work the same for local and paid models.
- Changing a price only changes future spend; past spend keeps the price of the day.
- The prices look arbitrary until they are backed by data. We revisit them once block 2 measures GPU cost per token on the cluster (option C).

## Addendum (2026-10-11): reranking

The `rerank` alias (LAB-184) is priced per query, as hosted rerankers are, not per token: **$1 per 1,000 queries**, half of Cohere's hosted reranker, since a query reranks up to 64 passages on a self-hosted model.
LiteLLM 1.104.2 prices every model of its `huggingface` provider, which TEI uses, at $0 whatever the configuration; the gateway's image fixes it at build time (`docker/litellm/patch_litellm.py`) until LiteLLM does.

## Addendum (2026-10-12): agent models

Two aliases for agents and production RAG (LAB-185):

- `chat-medium` (`qwen2.5:7b`, local) gets an internal price of **$1 / $4 per million tokens** in / out, twice `chat-large`, keeping the rule that a bigger local model costs more per token.
- `chat-pro` (Mistral Small 3.2 on Scaleway Generative APIs) carries **Scaleway's public price**, €0.15 / €0.35 per million tokens, counted as dollars: the euro is worth a little more, so the spend shown is within 10% of the bill.

The commercial price is lower than the internal price of the local 7B model. That is not a mistake: the internal prices are a chargeback convention, set before any measurement of GPU cost, and a shared hosted model is cheaper per token than a dev GPU running one model. They are to be revisited with the unit cost measured on the platform (LAB-138), as planned under option C.

A paid alias needs a spending cap of its own, not just the team's budget: LiteLLM caps the provider (`provider_budget_config`, $5 per 30 days at Scaleway), since caps per team and per model are Enterprise features.
