"""What a job is, how it runs, and what to do when it fails. No AMQP here, so it is tested without a broker.

A job is a JSON object:

    {"id": "season-2025-r01", "team": "f1", "alias": "chat-large",
     "messages": [{"role": "user", "content": "..."}], "max_tokens": 512}

The worker calls the gateway as the team, with the team's key: the team's aliases, budget, PII guardrail and Langfuse
project apply as for a direct call. A job may instead ask to be simulated, for load tests without a model:
"simulate": {"seconds": 2.0, "error_rate": 0.1} waits about that long, then fails with that probability.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum

import openai

# A job asks for its answer length, within this bound: a job that asked for 32,000 tokens could cost a team's budget.
MAX_TOKENS = 4096
# A simulated duration varies by this much around what the job asks, like real model calls.
JITTER = 0.25


class InvalidJob(ValueError):
    """The job can never succeed as written: retrying it would only fail again."""


class SimulatedFailure(RuntimeError):
    """A failure injected by a simulated job."""


class Outcome(Enum):
    DONE = "done"
    # Rejected with requeue: RabbitMQ counts the failure, delays the next attempt and dead-letters the job after its
    # third failure (policy jobs-retry in llmops-platform).
    RETRY = "retry"
    # Rejected without requeue: dead-lettered at once.
    DEAD = "dead"


@dataclass
class Simulation:
    seconds: float
    error_rate: float = 0.0


@dataclass
class Job:
    team: str
    alias: str = ""
    messages: list[dict] = field(default_factory=list)
    max_tokens: int = 512
    id: str = ""
    simulate: Simulation | None = None

    @classmethod
    def parse(cls, body: dict, allow_simulation: bool) -> "Job":
        if not isinstance(body, dict):
            raise InvalidJob("a job is a JSON object")
        team = body.get("team")
        if not isinstance(team, str) or not team:
            raise InvalidJob("team is required")
        job_id = str(body.get("id", ""))
        if "simulate" in body:
            if not allow_simulation:
                raise InvalidJob("simulated jobs are disabled on this worker")
            spec = body["simulate"]
            try:
                simulation = Simulation(seconds=float(spec["seconds"]), error_rate=float(spec.get("error_rate", 0)))
            except (KeyError, TypeError, ValueError) as error:
                raise InvalidJob(f"simulate needs seconds, and optionally error_rate: {error}") from None
            if not (0 <= simulation.seconds <= 3600 and 0 <= simulation.error_rate <= 1):
                raise InvalidJob("simulate.seconds must be within 0-3600 and error_rate within 0-1")
            return cls(team=team, id=job_id, simulate=simulation)
        alias, messages = body.get("alias"), body.get("messages")
        if not isinstance(alias, str) or not alias:
            raise InvalidJob("alias is required")
        if not isinstance(messages, list) or not messages:
            raise InvalidJob("messages must be a non-empty list")
        max_tokens = body.get("max_tokens", 512)
        if not isinstance(max_tokens, int) or not 1 <= max_tokens <= MAX_TOKENS:
            raise InvalidJob(f"max_tokens must be an integer within 1-{MAX_TOKENS}")
        return cls(team=team, alias=alias, messages=messages, max_tokens=max_tokens, id=job_id)


async def run(job: Job, client: openai.AsyncOpenAI | None, rng: random.Random | None = None) -> dict:
    """Run a job and return its result. Raises on failure; outcome() tells what to do with the exception."""
    rng = rng or random.Random()
    start = time.monotonic()
    if job.simulate:
        await asyncio.sleep(job.simulate.seconds * rng.uniform(1 - JITTER, 1 + JITTER))
        if rng.random() < job.simulate.error_rate:
            raise SimulatedFailure("simulated failure")
        return {"id": job.id, "status": "done", "simulated": True, "seconds": round(time.monotonic() - start, 3)}
    if client is None:
        raise InvalidJob(f"no gateway key for team {job.team}")
    response = await client.chat.completions.create(
        model=job.alias, messages=job.messages, max_tokens=job.max_tokens,
        extra_body={"metadata": {"job_id": job.id, "source": "llmops-worker"}},
    )
    return {
        "id": job.id,
        "status": "done",
        "alias": job.alias,
        "content": response.choices[0].message.content,
        "usage": response.usage.model_dump() if response.usage else None,
        "seconds": round(time.monotonic() - start, 3),
    }


def outcome(error: BaseException) -> Outcome:
    """Whether a failed job is worth another attempt."""
    if isinstance(error, InvalidJob):
        return Outcome.DEAD
    # A refused key, an alias the team may not use, a budget spent, a bad request: the same job fails again.
    # 408 and 429 are transient, as are 5xx (a model server down, a timeout) and connection errors.
    if isinstance(error, openai.APIStatusError) and error.status_code < 500 and error.status_code not in (408, 429):
        return Outcome.DEAD
    return Outcome.RETRY
