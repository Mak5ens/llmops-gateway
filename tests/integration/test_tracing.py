"""Tracing: every call through the gateway reaches the Langfuse project of its team, with the cost LiteLLM charged,
and without the messages. A team's lead sees that project and no other.

Chat calls use LiteLLM's mock_response: the answer does not matter, and the trace, its tokens and its cost are
built the same way. Each call carries a unique generation_name, which names its observation in Langfuse.
"""

import json
import time
import uuid

import httpx
import openai
import pytest
from helpers import (
    LANGFUSE_ADMIN,
    LANGFUSE_LEADS,
    LANGFUSE_PROJECT_KEYS,
    LANGFUSE_URL,
    MASTER_KEY,
    TEAMS,
    client_for,
    langfuse_session,
    run_bootstrap,
)
from openai import OpenAI
from test_pii_guardrail import DEMO, user

# (team, alias it calls): the three aliases, one per team.
CALLS = [("f1", "chat-small"), ("mj", "chat-large"), ("baux", "embed")]


def call(client: OpenAI, alias: str, name: str, text: str = "Bonjour", **extra):
    """Call an alias under a unique observation name and return the raw response, whose headers give the cost."""
    body = {"metadata": {"generation_name": name}, **extra}
    if alias == "embed":
        return client.embeddings.with_raw_response.create(model=alias, input=text, extra_body=body)
    body.setdefault("mock_response", "Bonjour !")
    return client.chat.completions.with_raw_response.create(model=alias, messages=user(text), extra_body=body)


def observations(project: str, **params) -> list[dict]:
    fields = "core,basic,usage,model,metadata,io"
    with httpx.Client(base_url=LANGFUSE_URL, auth=LANGFUSE_PROJECT_KEYS[project], timeout=30) as client:
        response = client.get("/api/public/v2/observations", params={"fields": fields, **params})
        response.raise_for_status()
        return response.json()["data"]


def traced(project: str, name: str) -> list[dict]:
    """Observations of the project with this name, once they reached Langfuse (a few seconds after the call)."""
    deadline = time.monotonic() + 60
    while not (found := observations(project, name=name)) and time.monotonic() < deadline:
        time.sleep(1)
    return found


def unique_name() -> str:
    return f"test-{uuid.uuid4().hex}"


@pytest.mark.parametrize(("team", "alias"), CALLS)
def test_a_call_is_traced_to_the_project_of_its_team(mock_client, team, alias):
    name = unique_name()
    response = call(mock_client(team), alias, name)

    [generation] = traced(team, name)
    team_metadata = generation["metadata"]["attributes.metadata"]
    assert (team_metadata["user_api_key_team_id"], team_metadata["user_api_key_alias"]) == (team, f"{team}-tests")
    assert generation["model"] == alias
    assert generation["usageDetails"]["input"] > 0
    assert generation["latency"] is not None
    # Langfuse prices the tokens with the same internal prices as LiteLLM (scripts/bootstrap_langfuse.py).
    assert generation["totalCost"] == pytest.approx(float(response.headers["x-litellm-response-cost"]))
    for other in LANGFUSE_PROJECT_KEYS.keys() - {team}:
        assert observations(other, name=name) == [], f"the call of {team} also reached {other}"


def test_a_streamed_call_is_priced_too(mock_client):
    # A streamed call's trace carries the model behind the alias instead of the alias: it must get the same price.
    name = unique_name()
    stream = mock_client("support").chat.completions.create(
        model="chat-large", messages=user("Bonjour"), stream=True, stream_options={"include_usage": True},
        extra_body={"metadata": {"generation_name": name}, "mock_response": "Bonjour !"},
    )
    usage = [chunk.usage for chunk in stream if chunk.usage][-1]

    [generation] = traced("support", name)
    input_price, output_price = 0.0000005, 0.000002  # chat-large in config/litellm.yaml
    expected = usage.prompt_tokens * input_price + usage.completion_tokens * output_price
    assert generation["totalCost"] == pytest.approx(expected)


def test_a_call_without_a_team_is_traced_to_the_gateway_project():
    name = unique_name()
    call(client_for(MASTER_KEY), "chat-small", name)
    assert len(traced("gateway", name)) == 1


def test_a_failed_call_is_traced_as_an_error(mock_client):
    name = unique_name()
    with pytest.raises(openai.InternalServerError):
        call(mock_client("mj"), "chat-small", name, mock_response="litellm.InternalServerError", num_retries=0)
    assert [generation["level"] for generation in traced("mj", name)] == ["ERROR"]


def test_traces_hold_no_message_and_no_personal_data(mock_client):
    # The pii-fr guardrail puts the real values back into the answer, before LiteLLM logs it: the trace must not
    # keep the messages. The guardrail's own observation keeps the types and positions of what it masked.
    name = unique_name()
    mock = "Dossier de <PERSON_1>, virement sur <IBAN_CODE_3>."
    response = call(mock_client("support"), "chat-large", name, DEMO, mock_response=mock).parse()
    assert "Marie Dupont" in response.choices[0].message.content

    [generation] = traced("support", name)
    assert "redacted-by-litellm" in generation["input"]
    assert "redacted-by-litellm" in generation["output"]
    trace = observations("support", traceId=generation["traceId"])
    for value in ("Marie", "Dupont", "rue de la Paix", "FR76", "06 12 34 56 78"):
        assert value not in json.dumps(trace)
    [guardrail] = [observation for observation in trace if observation["type"] == "GUARDRAIL"]
    assert guardrail["metadata"]["attributes.masked_entity_count"] == {
        "PERSON": 2, "FR_ADDRESS": 1, "IBAN_CODE": 1, "PHONE_NUMBER": 1
    }


@pytest.mark.parametrize("team", TEAMS)
def test_a_team_lead_sees_the_project_of_the_team_only(team):
    organizations = langfuse_session(*LANGFUSE_LEADS[team])["user"]["organizations"]
    seen = [(org["id"], org["role"], [project["id"] for project in org["projects"]]) for org in organizations]
    assert seen == [(team, "VIEWER", [team])]


def test_the_platform_admin_owns_every_project():
    organizations = langfuse_session(*LANGFUSE_ADMIN)["user"]["organizations"]
    projects = {project["id"] for org in organizations if org["role"] == "OWNER" for project in org["projects"]}
    assert projects == set(LANGFUSE_PROJECT_KEYS)


def test_a_second_bootstrap_duplicates_nothing():
    run_bootstrap()
    for project, keys in LANGFUSE_PROJECT_KEYS.items():
        with httpx.Client(base_url=LANGFUSE_URL, auth=keys, timeout=30) as client:
            models = client.get("/api/public/models", params={"limit": 100}).json()["data"]
        assert sorted(m["modelName"] for m in models if not m["isLangfuseManaged"]) == [
            "chat-large", "chat-small", "embed"
        ], project
    assert langfuse_session(*LANGFUSE_LEADS["baux"])["user"]["email"] == LANGFUSE_LEADS["baux"][0]
