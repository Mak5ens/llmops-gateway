import random

import httpx2
import openai
import pytest
from llmops_worker.jobs import (
    END_USER,
    MAX_TOKENS,
    InvalidJob,
    Job,
    Outcome,
    SimulatedFailure,
    outcome,
    run,
)

CHAT = {"id": "j1", "team": "f1", "alias": "chat-small", "messages": [{"role": "user", "content": "Bonjour"}]}


def test_parses_a_chat_job():
    job = Job.parse(CHAT, allow_simulation=False)
    assert (job.id, job.team, job.alias, job.max_tokens, job.simulate) == ("j1", "f1", "chat-small", 512, None)


def test_parses_a_simulated_job_when_allowed():
    job = Job.parse({"team": "f1", "simulate": {"seconds": 2, "error_rate": 0.1}}, allow_simulation=True)
    assert (job.simulate.seconds, job.simulate.error_rate) == (2.0, 0.1)


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ([], "a job is a JSON object"),
        ({"alias": "chat-small", "messages": CHAT["messages"]}, "team is required"),
        ({"team": "f1", "messages": CHAT["messages"]}, "alias is required"),
        ({"team": "f1", "alias": "chat-small", "messages": []}, "messages must be a non-empty list"),
        (CHAT | {"max_tokens": MAX_TOKENS + 1}, "max_tokens"),
        (CHAT | {"max_tokens": "512"}, "max_tokens"),
        ({"team": "f1", "simulate": {}}, "simulate needs seconds"),
        ({"team": "f1", "simulate": {"seconds": 1, "error_rate": 2}}, "error_rate within 0-1"),
    ],
)
def test_rejects_invalid_jobs(body, reason):
    with pytest.raises(InvalidJob, match=reason):
        Job.parse(body, allow_simulation=True)


def test_simulation_is_refused_unless_allowed():
    with pytest.raises(InvalidJob, match="disabled"):
        Job.parse({"team": "f1", "simulate": {"seconds": 1}}, allow_simulation=False)


async def test_simulated_job_waits_about_its_duration():
    job = Job.parse({"id": "s", "team": "f1", "simulate": {"seconds": 0.2}}, allow_simulation=True)
    result = await run(job, client=None, rng=random.Random(1))
    assert result["simulated"] and 0.15 <= result["seconds"] <= 0.3


async def test_simulated_job_fails_at_its_error_rate():
    job = Job.parse({"team": "f1", "simulate": {"seconds": 0, "error_rate": 1}}, allow_simulation=True)
    with pytest.raises(SimulatedFailure):
        await run(job, client=None)


async def test_a_team_without_key_is_invalid():
    with pytest.raises(InvalidJob, match="no gateway key"):
        await run(Job.parse(CHAT, allow_simulation=False), client=None)


def status_error(code: int) -> openai.APIStatusError:
    response = httpx2.Response(code, request=httpx2.Request("POST", "http://gateway/v1/chat/completions"))
    return openai.APIStatusError("error", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (InvalidJob("bad"), Outcome.DEAD),
        (status_error(400), Outcome.DEAD),  # bad request, budget exceeded
        (status_error(401), Outcome.DEAD),  # refused key
        (status_error(403), Outcome.DEAD),  # alias not allowed for the team
        (status_error(408), Outcome.RETRY),
        (status_error(429), Outcome.RETRY),  # rate limit
        (status_error(500), Outcome.RETRY),
        (status_error(503), Outcome.RETRY),
        (openai.APIConnectionError(request=httpx2.Request("POST", "http://gateway")), Outcome.RETRY),
        (SimulatedFailure("x"), Outcome.RETRY),
        (RuntimeError("unexpected"), Outcome.RETRY),
    ],
)
def test_outcome(error, expected):
    assert outcome(error) is expected


async def test_calls_the_gateway_as_the_worker_end_user():
    calls = []

    class Completions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return openai.types.chat.ChatCompletion.model_validate({
                "id": "c1", "object": "chat.completion", "created": 0, "model": "chat-small",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Bonjour"}}],
            })

    client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    result = await run(Job.parse(CHAT, allow_simulation=False), client)

    assert result["content"] == "Bonjour"
    assert calls[0]["user"] == END_USER == "llmops-worker"
