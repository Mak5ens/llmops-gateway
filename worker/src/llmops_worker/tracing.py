"""OpenTelemetry traces of the jobs, sent over OTLP when OTEL_EXPORTER_OTLP_ENDPOINT is set (to the platform's
collector, then Tempo), and a no-op otherwise.

A publisher that sends a W3C traceparent header with the job gets the worker's span in its own trace.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

tracer = trace.get_tracer("llmops_worker")


def setup() -> None:
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # OTEL_SERVICE_NAME overrides the default name.
    provider = TracerProvider(resource=Resource.create({"service.name": "llmops-worker"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)


def shutdown() -> None:
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()


@contextmanager
def job_span(message, queue: str, attempt: int) -> Iterator[trace.Span]:
    headers = {key: str(value) for key, value in (message.headers or {}).items()}
    with tracer.start_as_current_span(
        f"process {queue}",
        context=propagate.extract(headers),
        kind=SpanKind.CONSUMER,
        attributes={"messaging.system": "rabbitmq", "messaging.destination.name": queue,
                    "messaging.message.id": message.message_id or "", "job.attempt": attempt},
    ) as span:
        yield span


def record_failure(span: trace.Span, error: BaseException, decision: str) -> None:
    span.record_exception(error)
    span.set_attribute("job.outcome", decision)
    span.set_status(Status(StatusCode.ERROR, type(error).__name__))
