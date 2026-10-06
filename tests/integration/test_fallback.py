"""Fallback: when the chat-large server goes down, chat-large still answers, served by chat-small.

Worst case on purpose: chat-large is called first, so the gateway holds an open connection to the server
that then disappears.
"""

import time

import pytest
from helpers import STACK, ask

# chat-large timeout (20 s in config/litellm.yaml), then the answer from chat-small.
MAX_SECONDS = 30


@pytest.fixture
def chat_large_outage():
    STACK.stop("ollama-large")
    yield
    STACK.restart("ollama-large")


@pytest.mark.disruptive
def test_chat_large_falls_back_to_chat_small(team_client, request):
    client = team_client("f1")
    assert ask(client, "chat-large").headers["x-litellm-model-group"] == "chat-large"

    request.getfixturevalue("chat_large_outage")
    start = time.perf_counter()
    raw = ask(client, "chat-large", max_tokens=20)
    elapsed = time.perf_counter() - start

    assert raw.parse().choices[0].message.content.strip()
    assert raw.headers["x-litellm-model-group"] == "chat-small"
    assert elapsed < MAX_SECONDS, f"fallback took {elapsed:.1f}s"
    assert "Falling back to model_group = chat-small" in STACK.logs("litellm", since="60s")
