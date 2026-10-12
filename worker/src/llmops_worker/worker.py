"""The consumer: one AMQP connection, up to `concurrency` jobs at a time, and a clean stop.

A job is acknowledged only once it is done and its result sent: a worker that dies holding a job gives it back to
RabbitMQ, which counts it as a failure. On SIGTERM (a pod scaled down by KEDA, a rollout), the worker stops taking jobs,
finishes the ones it holds, then exits: none is lost, and none is counted as failed. The pod's grace period must
exceed the longest job.
"""

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass

import aio_pika
import openai
from aio_pika.abc import AbstractIncomingMessage

from . import tracing
from .jobs import InvalidJob, Job, Outcome, outcome, run

log = logging.getLogger("llmops_worker")


@dataclass
class Settings:
    amqp_url: str
    gateway_url: str
    queue: str = "jobs.inference"
    concurrency: int = 1
    allow_simulation: bool = False
    # Model calls can be slow on CPU: a job's call to the gateway gives up after this, and is retried.
    gateway_timeout: float = 120.0

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            amqp_url=os.environ["AMQP_URL"],
            gateway_url=os.environ["GATEWAY_URL"],
            queue=os.environ.get("WORKER_QUEUE", cls.queue),
            concurrency=int(os.environ.get("WORKER_CONCURRENCY", cls.concurrency)),
            allow_simulation=os.environ.get("WORKER_ALLOW_SIMULATION", "false").lower() == "true",
            gateway_timeout=float(os.environ.get("WORKER_GATEWAY_TIMEOUT", cls.gateway_timeout)),
        )


def team_keys() -> dict[str, str]:
    """Gateway keys of the teams, from TEAM_KEY_<TEAM> variables: a job runs with its team's key."""
    prefix = "TEAM_KEY_"
    return {name[len(prefix):].lower(): value for name, value in os.environ.items() if name.startswith(prefix) and value}


class Worker:
    def __init__(self, settings: Settings, keys: dict[str, str]) -> None:
        self.settings = settings
        # max_retries=0: a failed call goes back to RabbitMQ, which delays and counts the attempts.
        self.clients = {
            team: openai.AsyncOpenAI(base_url=settings.gateway_url, api_key=key, max_retries=0,
                                     timeout=settings.gateway_timeout)
            for team, key in keys.items()
        }
        self.in_flight: set[asyncio.Task] = set()
        self.channel: aio_pika.abc.AbstractChannel | None = None

    async def handle(self, message: AbstractIncomingMessage) -> None:
        task = asyncio.current_task()
        self.in_flight.add(task)
        try:
            await self._handle(message)
        finally:
            self.in_flight.discard(task)

    async def _handle(self, message: AbstractIncomingMessage) -> None:
        attempt = int((message.headers or {}).get("x-delivery-count", 0)) + 1
        with tracing.job_span(message, self.settings.queue, attempt) as span:
            try:
                try:
                    body = json.loads(message.body)
                except ValueError:
                    raise InvalidJob("the body is not JSON") from None
                job = Job.parse(body, self.settings.allow_simulation)
                span.set_attributes({"job.id": job.id, "job.team": job.team, "job.alias": job.alias,
                                     "job.simulated": job.simulate is not None})
                result = await run(job, self.clients.get(job.team))
                if message.reply_to:
                    await self.channel.default_exchange.publish(
                        aio_pika.Message(json.dumps(result).encode(), content_type="application/json",
                                         correlation_id=message.correlation_id),
                        routing_key=message.reply_to,
                    )
                await message.ack()
                log.info("job %s done in %.2f s (attempt %d)", job.id, result["seconds"], attempt)
            except Exception as error:  # noqa: BLE001 - every failure ends in a reject, with or without requeue
                decision = outcome(error)
                tracing.record_failure(span, error, decision.value)
                # basic.reject, not basic.nack: since RabbitMQ 4.0, only a reject counts towards the delivery limit.
                await message.reject(requeue=decision is Outcome.RETRY)
                log.warning("job failed on attempt %d (%s): %s: %s", attempt, decision.value, type(error).__name__,
                            error)

    async def serve(self) -> int:
        connection = await aio_pika.connect(self.settings.amqp_url)
        stop = asyncio.Event()
        lost = asyncio.Event()
        connection.close_callbacks.add(lambda *_: lost.set())
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)

        self.channel = await connection.channel()
        await self.channel.set_qos(prefetch_count=self.settings.concurrency)
        # The queue and its policy belong to the platform (or compose's RabbitMQ definitions): never declared here.
        queue = await self.channel.get_queue(self.settings.queue, ensure=True)
        tag = await queue.consume(self.handle)
        log.info("consuming %s, %d job(s) at a time, simulation %s", self.settings.queue, self.settings.concurrency,
                 "allowed" if self.settings.allow_simulation else "disabled")

        await asyncio.wait([asyncio.ensure_future(stop.wait()), asyncio.ensure_future(lost.wait())],
                           return_when=asyncio.FIRST_COMPLETED)
        if lost.is_set():
            log.error("connection to RabbitMQ lost")
            return 1
        log.info("stopping: no new job, waiting for %d in progress", len(self.in_flight))
        await queue.cancel(tag)
        if self.in_flight:
            await asyncio.gather(*self.in_flight, return_exceptions=True)
        await connection.close()
        log.info("stopped")
        return 0
