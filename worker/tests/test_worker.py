"""The consumer's decisions on fake AMQP messages: ack after the reply, reject with or without requeue."""

import asyncio
import json
from dataclasses import dataclass, field

import httpx2
import openai
import pytest
from llmops_worker import worker as worker_module
from llmops_worker.worker import Settings, Worker, team_keys


@dataclass
class FakeMessage:
    body: bytes
    headers: dict = field(default_factory=dict)
    reply_to: str | None = None
    correlation_id: str | None = None
    message_id: str | None = None
    acked: bool = False
    rejected: bool | None = None  # requeue flag once rejected
    nacked: bool | None = None  # requeue flag once nacked

    async def ack(self):
        self.acked = True

    async def nack(self, requeue: bool = True):
        self.nacked = requeue

    async def reject(self, requeue: bool = False):
        self.rejected = requeue


class FakeExchange:
    def __init__(self):
        self.published = []

    async def publish(self, message, routing_key):
        self.published.append((routing_key, message))


class FakeChannel:
    def __init__(self):
        self.default_exchange = FakeExchange()


@pytest.fixture
def worker() -> Worker:
    w = Worker(Settings(amqp_url="amqp://", gateway_url="http://gateway", allow_simulation=True), keys={})
    w.channel = FakeChannel()
    return w


def message(body, **kwargs) -> FakeMessage:
    return FakeMessage(body=json.dumps(body).encode(), **kwargs)


async def test_done_job_is_acked_after_its_reply(worker):
    msg = message({"id": "s1", "team": "f1", "simulate": {"seconds": 0}}, reply_to="replies", correlation_id="c1")
    await worker.handle(msg)
    assert msg.acked and msg.rejected is None
    routing_key, reply = worker.channel.default_exchange.published[0]
    assert routing_key == "replies" and reply.correlation_id == "c1"
    assert json.loads(reply.body) | {"seconds": 0} == {"id": "s1", "status": "done", "simulated": True, "seconds": 0}


async def test_done_job_without_reply_to_is_acked(worker):
    msg = message({"team": "f1", "simulate": {"seconds": 0}})
    await worker.handle(msg)
    assert msg.acked and not worker.channel.default_exchange.published


async def test_failed_job_is_rejected_with_requeue(worker):
    msg = message({"team": "f1", "simulate": {"seconds": 0, "error_rate": 1}}, headers={"x-delivery-count": 1})
    await worker.handle(msg)
    assert msg.rejected is True and not msg.acked


@pytest.mark.parametrize("body", [b"not json", json.dumps({"alias": "chat-small"}).encode()])
async def test_invalid_job_is_dead_lettered_at_once(worker, body):
    msg = FakeMessage(body=body)
    await worker.handle(msg)
    assert msg.rejected is False and not msg.acked


async def test_job_of_a_team_without_key_is_dead_lettered(worker):
    msg = message({"team": "f1", "alias": "chat-small", "messages": [{"role": "user", "content": "x"}]})
    await worker.handle(msg)
    assert msg.rejected is False


async def test_rate_limited_job_is_given_back_without_spending_an_attempt(worker, monkeypatch):
    class Completions:
        async def create(self, **kwargs):
            response = httpx2.Response(429, headers={"retry-after": "60"},
                                       request=httpx2.Request("POST", "http://gateway/v1/chat/completions"))
            raise openai.RateLimitError("Rate limit exceeded", response=response, body=None)

    worker.clients["f1"] = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    monkeypatch.setattr(worker_module, "backoff_seconds", lambda error: 0.01)
    msg = message({"team": "f1", "alias": "chat-pro", "messages": [{"role": "user", "content": "x"}]})
    await worker.handle(msg)
    # nack, not reject: RabbitMQ 4 counts only rejects towards the delivery limit.
    assert msg.nacked is True and msg.rejected is None and not msg.acked


async def test_a_stopping_worker_gives_a_rate_limited_job_back_at_once(worker, monkeypatch):
    class Completions:
        async def create(self, **kwargs):
            response = httpx2.Response(429, request=httpx2.Request("POST", "http://gateway/v1/chat/completions"))
            raise openai.RateLimitError("Rate limit exceeded", response=response, body=None)

    worker.clients["f1"] = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    monkeypatch.setattr(worker_module, "backoff_seconds", lambda error: 3600)
    worker.stopping.set()
    msg = message({"team": "f1", "alias": "chat-pro", "messages": [{"role": "user", "content": "x"}]})
    await asyncio.wait_for(worker.handle(msg), timeout=5)
    assert msg.nacked is True


def test_team_keys_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("TEAM_KEY_F1", "sk-f1")
    monkeypatch.setenv("TEAM_KEY_EMPTY", "")
    assert team_keys().get("f1") == "sk-f1" and "empty" not in team_keys()
