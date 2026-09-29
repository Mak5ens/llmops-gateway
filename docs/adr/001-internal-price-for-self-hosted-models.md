# ADR-001: Budget self-hosted models with an internal price per token

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
