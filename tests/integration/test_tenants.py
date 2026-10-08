"""Client teams: each one reaches only its aliases, and a team over its limits is blocked alone.

Limits and budgets are tested on a throwaway team (`temp_team`), so the real teams keep their spend.
"""

import openai
import pytest
from helpers import ask, run_bootstrap

# (team, allowed alias, forbidden alias), from config/tenants.yaml.
TEAM_ACCESS = [
    ("f1", "chat-small", None),
    ("mj", "chat-small", "embed"),
    ("baux", "embed", "chat-small"),
    ("support", "chat-small", "embed"),
]


def call(client, alias):
    if alias == "embed":
        return client.embeddings.create(model=alias, input="bonjour")
    return ask(client, alias)


@pytest.mark.parametrize(("team", "allowed", "forbidden"), TEAM_ACCESS)
def test_team_reaches_its_aliases_only(team_client, team, allowed, forbidden):
    client = team_client(team)
    call(client, allowed)

    if forbidden:
        # 403 since LiteLLM 1.84 (401 before): the key is valid, the model is not allowed to its team.
        with pytest.raises(openai.PermissionDeniedError) as refused:
            call(client, forbidden)
        assert refused.value.status_code == 403
        assert refused.value.body["type"] == "team_model_access_denied"


def test_rate_limit_blocks_the_key_and_not_other_teams(temp_team, new_key, team_client):
    client = new_key(team_id=temp_team, rpm_limit=2)
    ask(client, "chat-small")
    ask(client, "chat-small")

    with pytest.raises(openai.RateLimitError) as blocked:
        ask(client, "chat-small")
    assert "Rate limit exceeded" in blocked.value.message

    ask(team_client("f1"), "chat-small")


def test_budget_blocks_the_team_and_not_other_teams(admin, temp_team, new_key, team_client):
    client = new_key(team_id=temp_team)
    ask(client, "chat-small")
    # One call costs about $0.000005 at the internal price of chat-small (ADR-014): the team is now over budget.
    admin.post("/team/update", json={"team_id": temp_team, "max_budget": 0.000001}).raise_for_status()

    # 422 since LiteLLM 1.84 (400 before).
    with pytest.raises(openai.UnprocessableEntityError) as blocked:
        ask(client, "chat-small")
    assert blocked.value.body["type"] == "budget_exceeded"

    ask(team_client("f1"), "chat-small")


def test_bootstrap_is_idempotent(admin):
    # The session already ran the bootstrap once: a second run updates, and creates nothing.
    output = run_bootstrap()

    assert "created" not in output
    for team, _, _ in TEAM_ACCESS:
        keys = admin.get("/key/list", params={"team_id": team}).json()["keys"]
        assert len(keys) == 1, f"{team} has {len(keys)} keys"
