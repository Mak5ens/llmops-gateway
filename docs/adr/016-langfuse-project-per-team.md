# ADR-016: One Langfuse organization per team, provisioned in Langfuse's database

- **Status:** Accepted
- **Date:** 2026-09-30

## Context

LiteLLM sends a trace of every call to the self-hosted Langfuse (LAB-118): team, key, alias, tokens, cost, latency. The platform team keeps LiteLLM's admin UI and its keys and budgets. The lead of each client team should follow the calls and costs of their team in Langfuse, and see no other team's.

Langfuse grants access per organization and per project, not per trace. Checked in the source of v4.47.0:

- organization roles (Owner, Admin, Member, Viewer) are open source;
- project roles, which would let one organization hold every team, need the `rbac-project-roles` entitlement: Enterprise;
- the APIs that create organizations, projects, API keys and memberships (organization-scoped keys, `/api/admin/*`) need the `admin-api` entitlement: Enterprise too;
- with sign-up off (LAB-117), an account can only come from the `LANGFUSE_INIT_*` variables, which create one organization, one project and one user.

On LiteLLM's side, a team can have its own Langfuse keys, with no Enterprise check; `langfuse_otel` then exports that team's spans with those keys, to that team's project. In 1.83.14 they went into the team's metadata (`logging` with `callback_vars`); since 1.84 they go into `default_team_settings` of the config file (see Consequences).

## Options considered

| Option | Pros | Cons |
| -- | -- | -- |
| A. One organization and project per team, rows written by our bootstrap into Langfuse's PostgreSQL, as `LANGFUSE_INIT_*` does | Open source only; declared in `config/tenants.yaml` with the rest of the team; keys and passwords from `.env`, like the gateway keys; the team lead gets an account without opening sign-up | Couples the bootstrap to Langfuse's schema (5 tables) and to its hashing (bcrypt, salted SHA-256) |
| B. Same layout, created through the tRPC API the UI calls, signed in as the admin | Goes through Langfuse's own code | An internal API as well, with no contract; API keys come back random, so they must be carried to LiteLLM; accounts still need sign-up |
| C. Reopen sign-up: the admin invites each lead, who signs up | Langfuse's normal flow | Anyone reaching the UI can create an account; one manual step per team; still needs B or A for the rest |
| D. One project for everyone, a Langfuse account only for the platform team | Nothing to build | Leads cannot see their costs in Langfuse; they depend on the platform team |
| E. Langfuse Enterprise | Admin API and project roles | A licence for a portfolio platform |

## Decision

We choose **A**. For each team of `config/tenants.yaml` with a `langfuse` block, `scripts/bootstrap_langfuse.py` (run by `just gateway-up` and `just tenants`):

- writes the organization and the project (both named after the team id), the project's API keys and a Viewer account for the lead, with the same statements and hashes as Langfuse's `web/src/initialize.ts`, and makes the platform admin Owner of every organization;
- creates the price of each alias in every project through Langfuse's public API, from the internal prices of `config/litellm.yaml` (ADR-014), so Langfuse computes the cost LiteLLM charged;
- checks that `default_team_settings` in `config/litellm.yaml` points the team to its project, with a reference to the secret key (`os.environ/LANGFUSE_SECRET_KEY_<TEAM>`), not the key itself.

Calls without a team (the master key) stay in the Gateway project of `LANGFUSE_INIT_*`.

## Consequences

- A lead signs in with `<team>-lead@llmops.local` and sees one organization and one project; `tests/integration/test_tracing.py` checks it for every team, and that a call of one team reaches no other project.
- A Langfuse upgrade must be checked against the bootstrap: the version is pinned in `compose.langfuse.yaml`, and the tests fail if a table or a hash changes (sign-in of the leads, API keys of the teams).
- Traces carry no messages (`turn_off_message_logging` in `config/litellm.yaml`): the guardrail puts the real values back into the answer before LiteLLM logs it, and `langfuse_otel` ignores LiteLLM's per-team switch. A lead sees who called, which alias, the tokens, the cost, the latency and what the guardrail masked, not the content.
- Langfuse caches API keys in Redis: after a secret key changes in `.env`, the old one may work until the cache expires.
- On the cluster, the leads would sign in through SSO instead of a password, with the same organizations.
- Update, 2026-10-08 (LiteLLM 1.83.14 → 1.104.1, LAB-130): LiteLLM no longer resolves `os.environ/` references found in a team's metadata, a security fix, and ignored the teams' `logging` metadata, so their traces stopped reaching their projects (caught by `test_tracing.py`). The routing moved to `default_team_settings` in `config/litellm.yaml`, where references are still resolved, and the bootstrap no longer writes `logging` metadata. The secret keys still stay out of LiteLLM's database.
