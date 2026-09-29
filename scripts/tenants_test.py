"""Tenant test: each team only reaches its own aliases, and a team over its limits is blocked alone.

1. Every team key answers on an allowed alias and gets an explicit 401 on a forbidden one.
2. A throwaway team with rpm_limit 2 gets a 429 on its third call; the f1 key still answers.
3. The same team, given a budget of one millionth of a dollar, gets a 400 once spent; the f1 key still answers.
4. The bootstrap left exactly one key per team (run `just tenants` twice before to check idempotency).

Run with `just tenants-test` once `just gateway-up` has finished. The throwaway team is deleted at the end.
"""

import os
import sys

import httpx
from openai import APIStatusError, OpenAI

base_url = f"http://localhost:{os.environ.get('LITELLM_PORT', '4000')}"
admin = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {os.environ['LITELLM_MASTER_KEY']}"})
TEMP_TEAM = "limits-test"
failures = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {label}{f': {detail}' if detail else ''}")
    if not ok:
        failures.append(label)


def call(key: str, alias: str) -> tuple[int, str]:
    """Return (HTTP status, error type or 'answered') for one small call on an alias."""
    client = OpenAI(base_url=base_url, api_key=key, max_retries=0)
    try:
        if alias == "embed":
            client.embeddings.create(model=alias, input="bonjour")
        else:
            client.chat.completions.create(
                model=alias, messages=[{"role": "user", "content": "Say hi"}], max_tokens=5
            )
    except APIStatusError as error:
        body = error.body if isinstance(error.body, dict) else {}
        return error.status_code, str(body.get("type") or body.get("message") or error.message)[:120]
    return 200, "answered"


def admin_post(path: str, body: dict) -> dict:
    response = admin.post(path, json=body)
    response.raise_for_status()
    return response.json()


def delete_temp_team() -> None:
    admin.post("/team/delete", json={"team_ids": [TEMP_TEAM]})


# 1. Allowed and forbidden aliases, per team (see config/tenants.yaml).
teams = {
    "f1": (os.environ["TEAM_KEY_F1"], "chat-small", None),
    "mj": (os.environ["TEAM_KEY_MJ"], "chat-small", "embed"),
    "baux": (os.environ["TEAM_KEY_BAUX"], "embed", "chat-small"),
}
for team, (key, allowed, forbidden) in teams.items():
    status, detail = call(key, allowed)
    check(f"{team} calls {allowed}", status == 200, detail)
    if forbidden:
        status, detail = call(key, forbidden)
        check(f"{team} refused on {forbidden} with 401", status == 401, detail)

f1_key = teams["f1"][0]

# 2 and 3. A throwaway team, so the real teams keep their limits and spend.
delete_temp_team()
try:
    admin_post("/team/new", {"team_id": TEMP_TEAM, "models": ["chat-small"]})
    rpm_key = admin_post("/key/generate", {"team_id": TEMP_TEAM, "rpm_limit": 2})["key"]
    statuses = [call(rpm_key, "chat-small") for _ in range(3)]
    check(
        "rate limit: third call in the minute gets 429",
        [status for status, _ in statuses] == [200, 200, 429],
        f"{[status for status, _ in statuses]}",
    )

    # The budget is set afterwards: it is checked before the rate limit and would mask it.
    # The two calls above already cost more than this budget, so the next call on the team is refused.
    admin_post("/team/update", {"team_id": TEMP_TEAM, "max_budget": 0.000001, "budget_duration": "1d"})
    budget_key = admin_post("/key/generate", {"team_id": TEMP_TEAM})["key"]
    status, detail = call(budget_key, "chat-small")
    check("budget: exhausted team gets 400 budget_exceeded", status == 400 and "budget" in detail, detail)

    status, detail = call(f1_key, "chat-small")
    check("isolation: f1 still answers while the other team is blocked", status == 200, detail)
finally:
    delete_temp_team()

# 4. Idempotency of the bootstrap: one key per team, whatever the number of runs.
for team in teams:
    keys = admin.get("/key/list", params={"team_id": team}).json()["keys"]
    check(f"{team} has exactly one key", len(keys) == 1, f"{len(keys)} keys")

if failures:
    sys.exit(f"FAIL: {len(failures)} check(s) failed")
print("OK")
