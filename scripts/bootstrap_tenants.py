"""Create or update the client teams and their virtual keys from config/tenants.yaml.

Idempotent: a team or key that exists is updated to match the file, never duplicated.
Nothing is deleted. Runs in the `tenants-bootstrap` service on every `just gateway-up`, with the LiteLLM image,
which has every library it needs. Then sets up Langfuse for the teams: scripts/bootstrap_langfuse.py.
"""

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

import yaml

import bootstrap_langfuse

GATEWAY_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
MASTER_KEY = os.environ["LITELLM_MASTER_KEY"]
TENANTS_FILE = os.environ.get("TENANTS_FILE", "config/tenants.yaml")
LITELLM_CONFIG = os.environ.get("LITELLM_CONFIG", "config/litellm.yaml")

TEAM_FIELDS = ("team_alias", "models", "max_budget", "budget_duration")
KEY_FIELDS = ("key_alias", "rpm_limit", "tpm_limit")
# Guardrail of config/litellm.yaml that runs on every request unless the team opts out of it.
PII_GUARDRAIL = "pii-fr"


def check_langfuse_settings(teams: list[dict]) -> None:
    """Exit if a team's Langfuse project differs between tenants.yaml and default_team_settings in config/litellm.yaml.

    LiteLLM reads where to send a team's traces from its config file (ADR-016): the two files must agree, or a team's
    traces would go to another project, or to none.
    """
    with open(LITELLM_CONFIG) as file:
        settings = yaml.safe_load(file)["litellm_settings"].get("default_team_settings", [])
    configured = {s["team_id"]: (s.get("langfuse_public_key"), s.get("langfuse_secret_key")) for s in settings}
    for team in teams:
        if "langfuse" not in team:
            continue
        expected = (team["langfuse"]["public_key"], f"os.environ/{team['langfuse']['secret_key_env']}")
        if configured.get(team["team_id"]) != expected:
            sys.exit(f"team {team['team_id']}: default_team_settings in {LITELLM_CONFIG} must set "
                     f"langfuse_public_key {expected[0]} and langfuse_secret_key {expected[1]}")


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
    check_langfuse_settings(teams)

    # List endpoints rather than /team/info and /key/info: those log a stack trace for every missing object.
    _, existing_teams = call("GET", "/team/list")
    existing_team_ids = {team["team_id"] for team in existing_teams}

    for team in teams:
        team_id = team["team_id"]
        team_body = {"team_id": team_id} | {field: team[field] for field in TEAM_FIELDS}
        if team["pii_masking"] not in ("required", "optional"):
            sys.exit(f"team {team_id}: pii_masking must be 'required' or 'optional'")
        # LiteLLM reads the opt-out from the team metadata, which only the admin API can write.
        opted_out = [PII_GUARDRAIL] if team["pii_masking"] == "optional" else []
        team_body["metadata"] = {"opted_out_global_guardrails": opted_out}
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

    bootstrap_langfuse.main(teams)


if __name__ == "__main__":
    main()
