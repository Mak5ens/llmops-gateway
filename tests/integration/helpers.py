"""Settings and helpers shared by the tests and their fixtures.

Settings come from .env (created from .env.example when missing), as for `just gateway-up`.
"""

import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]

if not (ROOT / ".env").exists():
    shutil.copy(ROOT / ".env.example", ROOT / ".env")
load_dotenv(ROOT / ".env")

GATEWAY_URL = f"http://localhost:{os.environ.get('LITELLM_PORT', '4000')}"
MASTER_KEY = os.environ["LITELLM_MASTER_KEY"]
PRESIDIO_ANALYZER_URL = f"http://localhost:{os.environ.get('PRESIDIO_ANALYZER_PORT', '5002')}"
PRESIDIO_ANONYMIZER_URL = f"http://localhost:{os.environ.get('PRESIDIO_ANONYMIZER_PORT', '5001')}"
TEAM_KEYS = {
    "f1": os.environ["TEAM_KEY_F1"],
    "mj": os.environ["TEAM_KEY_MJ"],
    "baux": os.environ["TEAM_KEY_BAUX"],
}


def compose(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, capture_output=True, text=True)


def run_bootstrap() -> str:
    """Apply config/tenants.yaml, as `just tenants` does, and return what the script printed."""
    return compose("run", "--rm", "--no-deps", "tenants-bootstrap").stdout


def client_for(key: str) -> OpenAI:
    # No SDK retry: a test must see the gateway's first answer, 429 included.
    return OpenAI(base_url=GATEWAY_URL, api_key=key, max_retries=0)


def ask(client: OpenAI, alias: str, max_tokens: int = 5):
    """Short chat call; returns the raw response, whose headers say which alias served it."""
    return client.chat.completions.with_raw_response.create(
        model=alias, messages=[{"role": "user", "content": "Say hello in French."}], max_tokens=max_tokens
    )
