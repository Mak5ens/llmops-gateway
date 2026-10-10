"""No personal data leaks: the 100 annotated texts of the benchmark (benchmarks/dataset.jsonl) go through the gateway
with a key of a team under the pii-fr guardrail, then every annotated value is searched for:

1. in what the model received, read from the exact body LiteLLM sends to Ollama (logged at DEBUG only);
2. in Langfuse's traces, and in the logs of LiteLLM and Ollama at their usual level.

A value leaks when one of its words reaches them: "<LOCATION_1> Toussaint" leaks the surname of "Alexandrie Toussaint".
Words of a value that the text also uses outside its personal data ("rue", "de", an amount) do not count.

The model sees only the words Presidio is known to miss (benchmarks/results.md); the traces and logs see none.
Turning the guardrail off lets all 1,512 such words reach the model, and the test fails.
"""

import ast
import json
import re
import time
import uuid
from datetime import UTC, datetime

import pytest
from helpers import ROOT, STACK
from openai import OpenAI
from test_pii_guardrail import user
from test_tracing import observations

ROWS = [json.loads(line) for line in (ROOT / "benchmarks" / "dataset.jsonl").read_text().splitlines()]
# CI runs these tests in a job of their own, in parallel with the rest of the suite: the 100 real calls take about
# 3 minutes on a GitHub runner, which would bring the main job close to its 10-minute limit.
pytestmark = pytest.mark.leak

# What Presidio leaves in clear ("What Presidio left in clear" in benchmarks/results.md): (text, word).
# "Alexandrie" is taken for the city, so the first name is masked as a LOCATION and the surname stays.
# A change to the recognizers that masks one of them, or misses a new one, must update this list.
KNOWN_MISSES = {
    ("tax_letter-7", "Toussaint"),
    ("tax_letter-8", "Paris"),
    ("appointment_request-2", "Caen"),
}
WORD = re.compile(r"\w+")
# The line of LiteLLM's DEBUG log that holds the body sent to Ollama: -d '{'model': ..., 'messages': [...], ...}'
BODY_PREFIX = "-d '{'model'"


def private_words(row: dict) -> set[str]:
    """Words of the text's personal data that the rest of the text never uses."""
    text, public = row["text"], []
    cursor = 0
    for entity in sorted(row["entities"], key=lambda e: e["start"]):
        public.append(text[cursor : entity["start"]])
        cursor = entity["end"]
    public.append(text[cursor:])
    public_words = set(WORD.findall(" ".join(public)))
    return {word for entity in row["entities"] for word in WORD.findall(entity["value"])} - public_words


def leaks_in(row: dict, haystack: str) -> set[tuple[str, str]]:
    words = set(WORD.findall(haystack))
    return {(row["id"], word) for word in private_words(row) if word in words}


def distinctive(word: str) -> bool:
    """A word that cannot turn up in a log by chance, unlike "10" or "93" in ids and timestamps."""
    return (word.isalpha() and len(word) >= 4) or (word.isdigit() and len(word) >= 5)


def values_and_words_in(row: dict, haystack: str) -> set[tuple[str, str]]:
    """Whole values and distinctive private words of the row found in a trace or a log."""
    words = set(WORD.findall(haystack))
    found = {(row["id"], e["value"]) for e in row["entities"] if e["value"] in haystack}
    return found | {(row["id"], w) for w in private_words(row) if distinctive(w) and w in words}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@pytest.fixture
def masked_team(temp_team: str, new_key) -> OpenAI:
    """Client of a throwaway team on chat-small: no opt-out, so the pii-fr guardrail runs on every request."""
    return new_key(team_id=temp_team, metadata={"allow_client_mock_response": True})


@pytest.fixture
def litellm_at_debug():
    with STACK.litellm_at_debug():
        yield


@pytest.mark.disruptive
def test_the_model_receives_only_the_known_misses(masked_team, request):
    request.getfixturevalue("litellm_at_debug")
    since = now()
    # Real calls, one at a time, so the bodies in the log come in the order of the texts. One token is enough:
    # the prompt is what matters.
    for row in ROWS:
        masked_team.chat.completions.create(model="chat-small", messages=user(row["text"]), max_tokens=1)

    log = STACK.logs("litellm", since=since)
    lines = [line.strip() for line in log.splitlines()]
    bodies = [ast.literal_eval(line[len("-d '") : -1]) for line in lines if line.startswith(BODY_PREFIX)]
    # Fewer bodies than calls has had three causes: the log format changed with a LiteLLM version, the container log
    # was rotated during the calls (only the last ones are left), or the DEBUG pod was replaced (none are left).
    assert len(bodies) == len(ROWS), (
        f"{len(bodies)} request bodies in LiteLLM's DEBUG log for {len(ROWS)} calls: log format changed, log rotated "
        "during the calls, or LiteLLM restarted without DEBUG"
    )

    leaks = set()
    for row, body in zip(ROWS, bodies, strict=True):
        leaks |= leaks_in(row, json.dumps(body["messages"], ensure_ascii=False))
    assert leaks == KNOWN_MISSES


def test_traces_and_logs_hold_no_personal_data(masked_team):
    # mock_response keeps the calls fast: the guardrail, the logging and the trace run as for a real answer. The
    # answer names the first person, so the unmasked answer holds a real name too.
    since, name = now(), f"no-leak-{uuid.uuid4().hex}"
    for row in ROWS:
        masked_team.chat.completions.create(
            model="chat-small",
            messages=user(row["text"]),
            extra_body={"mock_response": "Réponse pour <PERSON_1>.", "metadata": {"generation_name": name}},
        )

    # A team without a Langfuse project of its own traces to Gateway. Traces arrive over a few seconds.
    deadline = time.monotonic() + 120
    while len(generations := observations("gateway", name=name, limit=1000)) < len(ROWS):
        assert time.monotonic() < deadline, f"{len(generations)} traces of {len(ROWS)} calls reached Langfuse"
        time.sleep(2)
    traces = json.dumps([observations("gateway", traceId=g["traceId"]) for g in generations], ensure_ascii=False)
    logs = STACK.logs("litellm", "ollama", since=since)

    found = {(where, *leak) for where, text in (("traces", traces), ("logs", logs)) for row in ROWS
             for leak in values_and_words_in(row, text)}
    assert found == set()
