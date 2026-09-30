"""Langfuse (compose.langfuse.yaml): the UI answers, the project and its keys exist from the first start,
and a span sent over OTLP goes through the whole pipeline (S3, Redis, the worker, ClickHouse)."""

import os
import time
from collections.abc import Iterator

import httpx
import pytest
from helpers import LANGFUSE_ADMIN, LANGFUSE_KEYS, LANGFUSE_URL


@pytest.fixture(scope="module")
def langfuse() -> Iterator[httpx.Client]:
    """Client of Langfuse's public API, authenticated with the keys of the Gateway project."""
    with httpx.Client(base_url=LANGFUSE_URL, auth=LANGFUSE_KEYS, timeout=30) as client:
        yield client


def sign_in(password: str) -> dict:
    """Sign in to the UI as the admin and return the session (empty when refused)."""
    with httpx.Client(base_url=LANGFUSE_URL, timeout=30) as client:
        csrf = client.get("/api/auth/csrf").json()["csrfToken"]
        form = {"email": LANGFUSE_ADMIN[0], "password": password, "csrfToken": csrf, "json": "true"}
        client.post("/api/auth/callback/credentials", data=form)
        return client.get("/api/auth/session").json()


def test_the_ui_answers():
    assert httpx.get(LANGFUSE_URL, follow_redirects=True).status_code == 200
    assert httpx.get(f"{LANGFUSE_URL}/api/public/health").json()["status"] == "OK"


def test_the_project_keys_are_created_on_first_start(langfuse):
    projects = langfuse.get("/api/public/projects").json()["data"]
    assert [project["name"] for project in projects] == ["Gateway"]


def test_a_wrong_secret_key_is_refused():
    response = httpx.get(f"{LANGFUSE_URL}/api/public/projects", auth=(LANGFUSE_KEYS[0], "sk-lf-wrong"))
    assert response.status_code == 401


def test_the_admin_can_sign_in():
    session = sign_in(LANGFUSE_ADMIN[1])
    assert session["user"]["email"] == LANGFUSE_ADMIN[0]
    assert sign_in("wrong-password") == {}


def test_sign_up_is_disabled():
    account = {"name": "Intruder", "email": "intruder@example.com", "password": "Password123!"}
    response = httpx.post(f"{LANGFUSE_URL}/api/auth/signup", json=account)
    assert response.status_code == 422


def test_a_span_sent_over_otlp_can_be_read_back(langfuse):
    # Langfuse v4 only takes traces over OTLP. The span goes to S3 (SeaweedFS), then through Redis to the worker,
    # which writes it to ClickHouse: reading it back checks every component.
    trace_id, now = os.urandom(16).hex(), time.time_ns()
    span = {"traceId": trace_id, "spanId": os.urandom(8).hex(), "name": "probe", "kind": 1,
            "startTimeUnixNano": str(now), "endTimeUnixNano": str(now + 1_000_000)}
    body = {"resourceSpans": [{"scopeSpans": [{"scope": {"name": "tests"}, "spans": [span]}]}]}
    langfuse.post("/api/public/otel/v1/traces", json=body).raise_for_status()

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        observations = langfuse.get("/api/public/v2/observations", params={"traceId": trace_id}).json()["data"]
        if observations:
            break
        time.sleep(1)
    assert [observation["name"] for observation in observations] == ["probe"]
