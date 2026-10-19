"""The rerank alias: a cross-encoder behind the gateway that rereads the candidates of a search, for the RAG of the
client apps (the F1 app asks in French about English rules). Allowed per team, priced per query, traced.
"""

import time
import uuid

import httpx
import pytest
from helpers import GATEWAY_URL, TEAM_KEYS
from test_tracing import traced

QUESTION = "Une équipe peut-elle changer les pneus pendant que la course est suspendue au drapeau rouge ?"
# Written for the test, in the style of a sporting regulation; only the third one answers the question.
PASSAGES = [
    "The safety car will be driven by an appointed driver and will carry an observer in radio contact with control.",
    "Each driver must use at least two different specifications of dry-weather tyres during the race.",
    "Whilst the race is suspended, teams may work on the cars and change tyres in the pit lane.",
    "A driver who leaves the track may rejoin only when it is safe to do so and without gaining an advantage.",
    "The pit lane speed limit is 80 km/h during practice, qualifying and the race.",
    "Should rain be forecast, intermediate tyres must be fitted before the car leaves the pit lane.",
]
ANSWER = 2
PRICE_PER_QUERY = 0.001  # config/litellm.yaml


def rerank(team: str, query: str, documents: list[str], **extra: object) -> httpx.Response:
    return httpx.post(
        f"{GATEWAY_URL}/rerank",
        headers={"Authorization": f"Bearer {TEAM_KEYS[team]}"},
        json={"model": "rerank", "query": query, "documents": documents, **extra},
        timeout=120,
    )


def test_a_french_question_ranks_the_english_answer_first() -> None:
    response = rerank("f1", QUESTION, PASSAGES)
    response.raise_for_status()

    results = response.json()["results"]
    assert len(results) == len(PASSAGES)
    assert results[0]["index"] == ANSWER
    assert results[0]["relevance_score"] > 0.5 > results[1]["relevance_score"]


def test_a_team_without_rerank_is_refused() -> None:
    # config/tenants.yaml: mj (game master assistant) has chat aliases only.
    response = rerank("mj", QUESTION, PASSAGES)

    assert response.status_code == 403
    assert "rerank" in response.text


def test_a_call_is_priced_per_query_and_traced_to_the_team() -> None:
    name = f"test-{uuid.uuid4().hex}"
    response = rerank("f1", QUESTION, PASSAGES, metadata={"generation_name": name})
    response.raise_for_status()

    # $0 here means the LiteLLM fix of docker/litellm/patch_litellm.py is missing from the running image.
    assert float(response.headers["x-litellm-response-cost"]) == pytest.approx(PRICE_PER_QUERY)
    [generation] = traced("f1", name)
    assert generation["totalCost"] == pytest.approx(PRICE_PER_QUERY)


def test_a_passage_longer_than_the_model_reads_is_truncated_not_refused() -> None:
    # The CPU model reads 512 tokens per (question, passage) pair; a whole article of a regulation is often longer.
    # A 422 here means LiteLLM sends `truncate: false` again, which overrides TEI's --auto-truncate: the patch of
    # docker/litellm/patch_litellm.py is missing from the running image.
    article = " ".join([PASSAGES[ANSWER]] + [PASSAGES[i] for i in range(len(PASSAGES)) if i != ANSWER] * 12)
    assert len(article.split()) > 700
    response = rerank("f1", QUESTION, [PASSAGES[0], article, PASSAGES[4]])
    response.raise_for_status()

    # The start of the passage, which is kept, holds the answer.
    assert response.json()["results"][0]["index"] == 1


def test_fifty_candidates_in_one_call() -> None:
    # A RAG reranks the 50 candidates of its hybrid search at once (compose.yaml: --max-client-batch-size=64).
    candidates = [f"{passage} (variant {i})" for i in range(9) for passage in PASSAGES][:50]
    start = time.monotonic()
    response = rerank("f1", QUESTION, candidates)
    elapsed = time.monotonic() - start
    response.raise_for_status()

    assert len(response.json()["results"]) == 50
    assert candidates[response.json()["results"][0]["index"]].startswith(PASSAGES[ANSWER])
    assert elapsed < 60, f"50 candidates took {elapsed:.1f} s"
