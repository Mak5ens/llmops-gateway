"""Nominal calls: each alias answers, served by its own model, with a team key."""

import pytest
from helpers import ask


@pytest.mark.parametrize("alias", ["chat-small", "chat-large"])
def test_chat_alias_answers(team_client, alias):
    raw = ask(team_client("f1"), alias, max_tokens=20)

    assert raw.parse().choices[0].message.content.strip()
    # No fallback on a healthy stack: the alias called is the one that answered.
    assert raw.headers["x-litellm-model-group"] == alias


def test_embed_alias_returns_768_dimensions(team_client):
    response = team_client("f1").embeddings.create(model="embed", input="Le locataire a payé son loyer en retard.")

    assert len(response.data[0].embedding) == 768
