"""Shared fixtures: start the stack once per session, and give tests admin and team clients.

The tests call the gateway like a client team would, with the OpenAI SDK and a virtual key.
"""

from collections.abc import Callable, Iterator

import httpx
import pytest
from helpers import GATEWAY_URL, MASTER_KEY, STACK, TEAM_KEYS, client_for, run_bootstrap
from openai import OpenAI


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # Tests that stop a service go last, so they cannot disturb the others.
    items.sort(key=lambda item: item.get_closest_marker("disruptive") is not None)


@pytest.fixture(scope="session", autouse=True)
def gateway() -> None:
    """Start the stack if needed (a no-op when it already runs) and create the client teams."""
    STACK.start()
    run_bootstrap()


@pytest.fixture(scope="session")
def admin() -> Iterator[httpx.Client]:
    """Client of the admin API, authenticated with the master key."""
    headers = {"Authorization": f"Bearer {MASTER_KEY}"}
    with httpx.Client(base_url=GATEWAY_URL, headers=headers, timeout=30) as client:
        yield client


@pytest.fixture
def team_client() -> Callable[[str], OpenAI]:
    """OpenAI client of a client team from config/tenants.yaml, by team id."""
    return lambda team: client_for(TEAM_KEYS[team])


@pytest.fixture
def mock_client(admin: httpx.Client) -> Iterator[Callable[[str], OpenAI]]:
    """Client of a test key of a team, allowed to send mock_response.

    Since LiteLLM 1.84, the proxy drops mock_response from a request unless the key or its team has
    allow_client_mock_response in its metadata: a client could otherwise skip the model. The teams' own keys keep that
    protection; these keys belong to the team, so its settings (aliases, guardrail opt-out, Langfuse project) apply,
    and they are deleted after the test, so each team still has one key for test_bootstrap_is_idempotent.
    """
    keys: dict[str, str] = {}

    def create(team: str) -> OpenAI:
        if team not in keys:
            body = {"team_id": team, "key_alias": f"{team}-tests", "metadata": {"allow_client_mock_response": True}}
            response = admin.post("/key/generate", json=body)
            response.raise_for_status()
            keys[team] = response.json()["key"]
        return client_for(keys[team])

    yield create
    if keys:
        admin.post("/key/delete", json={"keys": list(keys.values())}).raise_for_status()


@pytest.fixture
def temp_team(admin: httpx.Client) -> Iterator[str]:
    """Throwaway team allowed on chat-small, with no limit, deleted with its keys after the test.

    Tests on limits and budgets run on it, so the real teams keep their settings and spend.
    """
    team_id = "limits-test"
    if team_id in {team["team_id"] for team in admin.get("/team/list").json()}:
        admin.post("/team/delete", json={"team_ids": [team_id]}).raise_for_status()
    admin.post("/team/new", json={"team_id": team_id, "models": ["chat-small"]}).raise_for_status()
    yield team_id
    admin.post("/team/delete", json={"team_ids": [team_id]}).raise_for_status()


@pytest.fixture
def new_key(admin: httpx.Client) -> Callable[..., OpenAI]:
    """Create a virtual key with the given settings (team_id, rpm_limit...) and return its client."""

    def create(**settings) -> OpenAI:
        response = admin.post("/key/generate", json=settings)
        response.raise_for_status()
        return client_for(response.json()["key"])

    return create
