"""Create or update the client teams and their virtual keys from config/tenants.yaml.

Idempotent: a team or key that exists is updated to match the file, never duplicated.
Nothing is deleted. Runs in the `tenants-bootstrap` service on every `just gateway-up`,
and needs only the Python standard library and PyYAML (both in the LiteLLM image).
"""

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

import yaml

GATEWAY_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
MASTER_KEY = os.environ["LITELLM_MASTER_KEY"]
TENANTS_FILE = os.environ.get("TENANTS_FILE", "config/tenants.yaml")

TEAM_FIELDS = ("team_alias", "models", "max_budget", "budget_duration")
KEY_FIELDS = ("key_alias", "rpm_limit", "tpm_limit")


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        GATEWAY_URL + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def ensure(kind: str, exists: bool, create: str, update: str, body: dict) -> None:
    path = update if exists else create
    status, answer = call("POST", path, body)
    if status != 200:
        sys.exit(f"{kind}: {path} failed with HTTP {status}: {answer}")
    print(f"{kind}: {'updated' if exists else 'created'}")


def main() -> None:
    with open(TENANTS_FILE) as file:
        teams = yaml.safe_load(file)["teams"]

    # List endpoints rather than /team/info and /key/info: those log a stack trace for every missing object.
    _, existing_teams = call("GET", "/team/list")
    existing_team_ids = {team["team_id"] for team in existing_teams}

    for team in teams:
        team_id = team["team_id"]
        team_body = {"team_id": team_id} | {field: team[field] for field in TEAM_FIELDS}
        ensure(f"team {team_id}", team_id in existing_team_ids, "/team/new", "/team/update", team_body)

        key = team["key"]
        value = os.environ.get(key["value_env"], "")
        if not value.startswith("sk-"):
            sys.exit(f"team {team_id}: set {key['value_env']} in .env to a key starting with 'sk-'")
        # The key has no model list of its own: it inherits the aliases allowed for its team.
        key_body = {"key": value, "team_id": team_id} | {field: key[field] for field in KEY_FIELDS}
        # LiteLLM stores only the SHA-256 of each key, so a key is looked up by its hash.
        key_hash = hashlib.sha256(value.encode()).hexdigest()
        _, found = call("GET", f"/key/list?key_hash={key_hash}")
        ensure(f"key {key['key_alias']}", found["total_count"] > 0, "/key/generate", "/key/update", key_body)


if __name__ == "__main__":
    main()
