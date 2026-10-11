"""The job worker: a job published to the queue is run by the worker through the gateway, with its team's key, and
the answer comes back to the queue named in reply_to. A job the gateway refuses goes straight to the dead letter queue.

On Kubernetes, the worker scales from zero when the job arrives (KEDA, in llmops-platform): the first answer can take
the time of a pod start.
"""

import json
import time
import uuid

import pika
import pytest
from helpers import STACK

EXCHANGE, ROUTING_KEY, DEAD_LETTERS = "jobs", "inference", "jobs.inference.dead"
# Covers a worker scaled up from zero on the cluster, then a call to the model on CPU.
TIMEOUT = 180


@pytest.fixture(scope="module")
def channel():
    connection = pika.BlockingConnection(pika.URLParameters(STACK.amqp_url()))
    yield connection.channel()
    connection.close()


def publish(channel, job: dict, reply_to: str | None = None) -> str:
    correlation_id = str(uuid.uuid4())
    properties = pika.BasicProperties(content_type="application/json", correlation_id=correlation_id,
                                      reply_to=reply_to, delivery_mode=2)
    channel.basic_publish(EXCHANGE, ROUTING_KEY, json.dumps(job).encode(), properties)
    return correlation_id


def wait_for(channel, queue: str, match, timeout: float = TIMEOUT) -> dict:
    """First message of a queue whose decoded body satisfies match; the others are left in the queue."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        method, properties, body = channel.basic_get(queue)
        if method is None:
            time.sleep(1)
            continue
        message = {"properties": properties, "body": json.loads(body) if body.startswith(b"{") else body}
        if match(message):
            channel.basic_ack(method.delivery_tag)
            return message
        channel.basic_reject(method.delivery_tag, requeue=True)
    raise AssertionError(f"nothing matching in {queue} after {timeout} s")


def test_a_job_runs_through_the_gateway_and_replies(channel):
    replies = channel.queue_declare("", exclusive=True).method.queue
    job_id = f"test-{uuid.uuid4().hex[:8]}"
    correlation_id = publish(channel, {
        "id": job_id, "team": "f1", "alias": "chat-small", "max_tokens": 5,
        "messages": [{"role": "user", "content": "Say hello in French."}],
    }, reply_to=replies)

    reply = wait_for(channel, replies, lambda m: m["properties"].correlation_id == correlation_id)

    result = reply["body"]
    assert (result["id"], result["status"], result["alias"]) == (job_id, "done", "chat-small")
    assert result["content"].strip()
    # Counted by the gateway like any call of the team.
    assert result["usage"]["completion_tokens"] > 0


def test_a_job_the_gateway_refuses_is_dead_lettered_at_once(channel):
    # The support team may not use embed (config/tenants.yaml): the gateway answers 401, which retrying cannot fix.
    job_id = f"test-refused-{uuid.uuid4().hex[:8]}"
    publish(channel, {"id": job_id, "team": "support", "alias": "embed", "messages": [{"role": "user", "content": "x"}]})

    dead = wait_for(channel, DEAD_LETTERS, lambda m: isinstance(m["body"], dict) and m["body"].get("id") == job_id)

    death = dead["properties"].headers["x-death"][0]
    # Rejected without requeue on its first delivery, not after three attempts.
    assert (death["reason"], death["queue"], death["count"]) == ("rejected", "jobs.inference", 1)
