"""Demo of the gateway, as a client team sees it: `just demo`.

The lease team `baux` sends a message full of personal data, the model only gets markers, the answer comes back with
the real values, and the trace in Langfuse holds the team, the tokens and the cost, but no personal data.
"""

import json
import os
import sys
import textwrap
import time
import uuid
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

GATEWAY_URL = f"http://localhost:{os.environ.get('LITELLM_PORT', '4000')}"
LANGFUSE_URL = f"http://localhost:{os.environ.get('LANGFUSE_PORT', '3100')}"
TEAM, ALIAS = "baux", "chat-large"
MESSAGE = (
    "Bonjour, je suis Marie Dupont, locataire au 12 rue de la Paix, 75002 Paris. "
    "Mon loyer sera désormais prélevé sur le compte FR76 3000 6000 0112 3456 7890 189. "
    "Vous pouvez me joindre au 06 12 34 56 78."
)
TASK = (
    "Rédige un accusé de réception en deux phrases, "
    "qui reprend le nom de la locataire, son adresse et le nouveau compte."
)
# Small models sometimes drop the angle brackets, and a marker that does not match stays in the answer.
SYSTEM = (
    "Tu es l'assistant d'une agence immobilière. "
    "Recopie les marqueurs entre chevrons tels quels, par exemple <PERSON_1>."
)

BOLD, DIM, GREEN, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[0m"


def step(title: str, text: str, color: str = "") -> None:
    lines = [f"{color}{wrapped}{RESET}" for line in text.splitlines() for wrapped in textwrap.wrap(line, 90)]
    print(f"\n{BOLD}{title}{RESET}", *lines, sep="\n")


def masked(text: str) -> str:
    """The message as the model receives it: the platform runs the team's guardrail on it, with the master key."""
    response = httpx.post(
        f"{GATEWAY_URL}/guardrails/apply_guardrail",
        headers={"Authorization": f"Bearer {os.environ['LITELLM_MASTER_KEY']}"},
        json={"guardrail_name": "pii-fr", "text": text},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["response_text"]


def trace_of(name: str) -> list[dict]:
    """Observations of the call in the team's Langfuse project, read with that project's keys."""
    keys = (f"pk-lf-{TEAM}", os.environ[f"LANGFUSE_SECRET_KEY_{TEAM.upper()}"])
    with httpx.Client(base_url=LANGFUSE_URL, auth=keys, timeout=30) as langfuse:

        def observations(**params) -> list[dict]:
            fields = "core,basic,usage,model,metadata,io"
            return langfuse.get("/api/public/v2/observations", params={"fields": fields, **params}).json()["data"]

        # LiteLLM sends the trace a few seconds after the call.
        deadline = time.monotonic() + 60
        while not (generations := observations(name=name)):
            if time.monotonic() > deadline:
                sys.exit("The trace did not reach Langfuse within 60 s: is langfuse-worker running?")
            time.sleep(1)
        return observations(traceId=generations[0]["traceId"])


def main() -> None:
    client = OpenAI(base_url=GATEWAY_URL, api_key=os.environ[f"TEAM_KEY_{TEAM.upper()}"])
    name = f"demo-{uuid.uuid4().hex[:8]}"

    step(f"1. The team {TEAM} sends, with its own key, to the alias {ALIAS}:", MESSAGE)
    step("2. The pii-fr guardrail masks it. The model receives:", masked(MESSAGE), GREEN)

    response = client.chat.completions.create(
        model=ALIAS,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"{MESSAGE}\n\n{TASK}"}],
        temperature=0,
        extra_body={"metadata": {"generation_name": name}},
    )
    step("3. The model answers with markers, the gateway puts the values back:", response.choices[0].message.content)

    observations = trace_of(name)
    [generation] = [o for o in observations if o["name"] == name]
    # One guardrail span per message: the system message has nothing to mask.
    counts = Counter()
    for guardrail in (o for o in observations if o["type"] == "GUARDRAIL"):
        counts.update(guardrail["metadata"]["attributes.masked_entity_count"])
    team = generation["metadata"]["attributes.metadata"]["user_api_key_team_id"]
    tokens = generation["usageDetails"]
    prompt, answer = json.loads(generation["input"])[-1]["content"], json.loads(generation["output"])["content"]
    step(
        f"4. Its trace in Langfuse, project {TEAM} ({LANGFUSE_URL}):",
        f"team {team} · model {generation['model']} · {tokens['input']} tokens in, {tokens['output']} out"
        f" · ${generation['totalCost']:.6f} · {generation['latency']:.1f} s\n"
        f"masked: {', '.join(f'{entity} ×{count}' for entity, count in counts.items())}\n"
        f"prompt: {prompt} · answer: {answer}",
    )
    print(f"\n{DIM}No personal data in the trace: the prompts and answers are never logged (ADR-016).{RESET}")


if __name__ == "__main__":
    main()
