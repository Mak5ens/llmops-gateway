# Job worker

Long jobs (analysing a Formula 1 season, checking a batch of documents) go through a queue rather than a synchronous call to the gateway. The worker consumes the job queue of [llmops-platform](https://github.com/Mak5ens/llmops-platform) (RabbitMQ, queue `jobs.inference`), calls the gateway with the key of the job's team, and sends the answer back.
On the cluster, KEDA runs from zero to N workers depending on the length of the queue.

## A job

A job is a JSON message published to the exchange `jobs` with the routing key `inference`:

```json
{
  "id": "season-2025-r01",
  "team": "f1",
  "alias": "chat-large",
  "messages": [{"role": "user", "content": "..."}],
  "max_tokens": 512
}
```

- The worker calls the gateway as the team: the team's aliases, budget, PII guardrail and Langfuse project apply as for a direct call. Each team's key comes from a `TEAM_KEY_<TEAM>` variable.
- `max_tokens` defaults to 512, at most 4,096.
- When the message has a `reply_to` property, the result goes to that queue, with the job's `correlation_id`. Use an exclusive queue (server-named) or a durable one: RabbitMQ 4 no longer accepts transient shared queues.

```json
{"id": "season-2025-r01", "status": "done", "alias": "chat-large", "content": "...", "usage": {"prompt_tokens": 812, "completion_tokens": 240, "total_tokens": 1052}, "seconds": 3.42}
```

For load tests, a job can ask to be simulated instead of calling a model: `{"team": "f1", "simulate": {"seconds": 2, "error_rate": 0.1}}`. It waits about that long (±25 %), then fails with that probability. Simulation is refused unless the worker runs with `WORKER_ALLOW_SIMULATION=true`.

## Failures

The worker never retries by itself: it gives the job back to RabbitMQ, whose policy `jobs-retry` delays the next attempt (5 s times the number of failures) and dead-letters the job to `jobs.inference.dead` after its third failure.

| What happened | What the worker does | Then |
| -- | -- | -- |
| Done | acknowledges, after sending the reply | |
| Gateway error 5xx, 408 or 429, timeout, connection error, simulated failure | rejects with requeue | retried, dead-lettered after the third failure |
| Gateway error 4xx otherwise (refused key, alias not allowed, budget spent, bad request), invalid job | rejects without requeue | dead-lettered at once |
| The worker dies holding the job | nothing: the connection closes | RabbitMQ counts a failure and redelivers it |

A job is failed with `basic.reject`, never `basic.nack`: since RabbitMQ 4.0, only a reject counts towards the delivery limit, and a nacked job would come back forever.

On SIGTERM (a pod scaled down, a rollout), the worker stops taking jobs, finishes the ones it holds, acknowledges them and exits. The grace period of its pod must exceed the longest job.

## Settings

| Variable | Default | |
| -- | -- | -- |
| `AMQP_URL` | required | `amqp://user:password@host:5672/` |
| `GATEWAY_URL` | required | base URL of the gateway (OpenAI-compatible API) |
| `TEAM_KEY_<TEAM>` | | gateway key of each team the worker serves |
| `WORKER_QUEUE` | `jobs.inference` | |
| `WORKER_CONCURRENCY` | `1` | jobs at a time, the prefetch of the channel |
| `WORKER_ALLOW_SIMULATION` | `false` | accept simulated jobs |
| `WORKER_GATEWAY_TIMEOUT` | `120` | seconds before a gateway call is abandoned, then retried |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | | traces over OTLP/HTTP; none when unset |

Each job is a span `process jobs.inference` (OpenTelemetry), with its id, team, alias, attempt and outcome. A publisher that sends a W3C `traceparent` header gets it in its own trace.

## Develop

```bash
just test-worker        # unit tests, no broker: about a second
just gateway-up         # the compose stack includes RabbitMQ, its topology and the worker
just test tests/integration/test_worker.py
```

In the compose stack, `config/rabbitmq/definitions.json` holds the same exchanges, queues and policy as `platform/job-queue/` in llmops-platform, imported by the one-shot `rabbitmq-topology` service. Keep both in step.
