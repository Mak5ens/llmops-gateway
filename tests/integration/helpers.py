"""Settings and helpers shared by the tests and their fixtures.

The tests run against the Compose stack (default) or the gateway deployed on Kubernetes (GATEWAY_STACK=kubernetes),
see stacks.py. Compose settings come from .env (created from .env.example when missing), as for `just gateway-up`;
Kubernetes settings from the cluster, with the same variable names.
"""

import os
import shutil

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from stacks import ROOT, KubernetesStack, from_environment

STACK = from_environment()
if isinstance(STACK, KubernetesStack):
    os.environ.update(STACK.settings())
else:
    if not (ROOT / ".env").exists():
        shutil.copy(ROOT / ".env.example", ROOT / ".env")
    load_dotenv(ROOT / ".env")

GATEWAY_URL = STACK.gateway_url
MASTER_KEY = os.environ["LITELLM_MASTER_KEY"]
PRESIDIO_ANALYZER_URL = STACK.presidio_analyzer_url
PRESIDIO_ANONYMIZER_URL = STACK.presidio_anonymizer_url
LANGFUSE_URL = STACK.langfuse_url
LANGFUSE_KEYS = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
LANGFUSE_ADMIN = (os.environ["LANGFUSE_ADMIN_EMAIL"], os.environ["LANGFUSE_ADMIN_PASSWORD"])
TEAMS = ("f1", "mj", "baux", "support")
TEAM_KEYS = {team: os.environ[f"TEAM_KEY_{team.upper()}"] for team in TEAMS}
# API keys of each Langfuse project: Gateway, then one per team (config/tenants.yaml).
LANGFUSE_PROJECT_KEYS = {"gateway": LANGFUSE_KEYS} | {
    team: (f"pk-lf-{team}", os.environ[f"LANGFUSE_SECRET_KEY_{team.upper()}"]) for team in TEAMS
}
# Read-only account of each team's lead.
LANGFUSE_LEADS = {team: (f"{team}-lead@llmops.local", os.environ[f"LANGFUSE_VIEWER_PASSWORD_{team.upper()}"]) for team in TEAMS}


def run_bootstrap() -> str:
    """Apply config/tenants.yaml, as `just tenants` does, and return what the script printed."""
    return STACK.bootstrap()


def client_for(key: str) -> OpenAI:
    # No SDK retry: a test must see the gateway's first answer, 429 included.
    return OpenAI(base_url=GATEWAY_URL, api_key=key, max_retries=0)


def ask(client: OpenAI, alias: str, max_tokens: int = 5):
    """Short chat call; returns the raw response, whose headers say which alias served it."""
    return client.chat.completions.with_raw_response.create(
        model=alias, messages=[{"role": "user", "content": "Say hello in French."}], max_tokens=max_tokens
    )


def langfuse_session(email: str, password: str) -> dict:
    """Sign in to the Langfuse UI and return the session, with the organizations and projects the account sees.

    Empty when the sign-in is refused.
    """
    with httpx.Client(base_url=LANGFUSE_URL, timeout=30) as client:
        csrf = client.get("/api/auth/csrf").json()["csrfToken"]
        form = {"email": email, "password": password, "csrfToken": csrf, "json": "true"}
        client.post("/api/auth/callback/credentials", data=form)
        return client.get("/api/auth/session").json()
