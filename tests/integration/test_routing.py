"""Nominal calls: each alias answers, served by its own model, with a team key; the agent aliases follow a schema."""

import json
import os

import pytest
from helpers import ask
from pydantic import BaseModel

# chat-pro calls Scaleway with the gateway's key: without one (a fork's CI, a fresh clone), its tests are skipped.
needs_scaleway = pytest.mark.skipif(not os.environ.get("SCW_SECRET_KEY"), reason="SCW_SECRET_KEY is not set")
CHAT_ALIASES = ["chat-small", "chat-medium", "chat-large", pytest.param("chat-pro", marks=needs_scaleway)]
AGENT_ALIASES = ["chat-medium", pytest.param("chat-pro", marks=needs_scaleway)]


class Rewrite(BaseModel):
    """What a RAG asks of a model before searching: the question in English, with its season."""

    query: str
    season: int | None
    variants: list[str]


QUESTION = "En 2025, une pénalité de 5 secondes peut-elle être purgée pendant un arrêt au stand ?"
INSTRUCTIONS = (
    "Rewrite the Formula 1 question as a standalone English search query, give two English variants, and the season "
    f"it is about. Answer with one JSON object matching this JSON schema: {json.dumps(Rewrite.model_json_schema())}"
)


@pytest.mark.parametrize("alias", CHAT_ALIASES)
def test_chat_alias_answers(team_client, alias):
    raw = ask(team_client("f1"), alias, max_tokens=20)

    assert raw.parse().choices[0].message.content.strip()
    # No fallback on a healthy stack: the alias called is the one that answered.
    assert raw.headers["x-litellm-model-group"] == alias


@pytest.mark.parametrize("alias", AGENT_ALIASES)
def test_agent_alias_returns_json_valid_against_a_schema(team_client, alias):
    # JSON mode with the schema in the prompt works on every alias; a strict JSON schema made the small local
    # models loop on an array until the timeout.
    response = team_client("f1").chat.completions.create(
        model=alias,
        messages=[{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": QUESTION}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=300,
    )

    rewrite = Rewrite.model_validate_json(response.choices[0].message.content)
    assert rewrite.season == 2025
    assert "penalty" in rewrite.query.lower()
    assert len(rewrite.variants) == 2


def test_embed_alias_returns_768_dimensions(team_client):
    response = team_client("f1").embeddings.create(model="embed", input="Ma commande est arrivée avec trois jours de retard.")

    assert len(response.data[0].embedding) == 768
