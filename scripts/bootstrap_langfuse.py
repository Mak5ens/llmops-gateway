"""Give each client team its own Langfuse organization and project, with API keys and a read-only account.

Called by bootstrap_tenants.py for every team of config/tenants.yaml that has a `langfuse` block.
Why an organization per team, and why rows written into Langfuse's database: docs/adr/016-langfuse-project-per-team.md.

- The organization, the project, its API keys and the account are written to Langfuse's PostgreSQL, as Langfuse
  itself does for its LANGFUSE_INIT_* variables (web/src/initialize.ts, v4.47.0): its API for them is Enterprise.
  Hashes are computed the same way: bcrypt for the secret key and the password, SHA-256 salted with SALT for the
  fast lookup of the secret key.
- The prices of the aliases go through Langfuse's public API, from the internal prices of config/litellm.yaml, so
  Langfuse computes the same cost as LiteLLM (docs/adr/014-internal-price-for-self-hosted-models.md).

Re-running is safe: every row is created or updated to match the file and .env, never duplicated.
"""

import asyncio
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

import yaml
# LiteLLM's database client, already in its image; it runs plain SQL against any PostgreSQL.
from prisma import Prisma

LANGFUSE_URL = os.environ.get("LANGFUSE_URL", "http://langfuse-web:3000")
LITELLM_CONFIG = os.environ.get("LITELLM_CONFIG", "config/litellm.yaml")
KEY_NOTE = "Provisioned by scripts/bootstrap_langfuse.py"

# One statement per call: Prisma sends each one as a prepared statement.
# pgcrypto gives crypt() and gen_salt(), the bcrypt of Langfuse's bcryptjs; gen_random_uuid() is built in.
SQL_EXTENSION = "CREATE EXTENSION IF NOT EXISTS pgcrypto"
SQL_ORG = """
INSERT INTO organizations (id, name) VALUES ($1, $2)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = now()
"""
SQL_PROJECT = """
INSERT INTO projects (id, org_id, name) VALUES ($1, $2, $3)
ON CONFLICT (id) DO UPDATE SET org_id = EXCLUDED.org_id, name = EXCLUDED.name, updated_at = now()
"""
# bcrypt cost 11 for secret keys and 12 for passwords, as in Langfuse. A hash is only replaced when the secret changed.
SQL_API_KEY = f"""
INSERT INTO api_keys (id, public_key, hashed_secret_key, fast_hashed_secret_key, display_secret_key, note, project_id,
                      scope)
VALUES (gen_random_uuid()::text, $1, crypt($2, gen_salt('bf', 11)), $3, $4, '{KEY_NOTE}', $5, 'PROJECT')
ON CONFLICT (public_key) DO UPDATE SET
    hashed_secret_key = EXCLUDED.hashed_secret_key,
    fast_hashed_secret_key = EXCLUDED.fast_hashed_secret_key,
    display_secret_key = EXCLUDED.display_secret_key,
    project_id = EXCLUDED.project_id
WHERE api_keys.fast_hashed_secret_key IS DISTINCT FROM EXCLUDED.fast_hashed_secret_key
   OR api_keys.project_id IS DISTINCT FROM EXCLUDED.project_id
"""
SQL_USER = """
INSERT INTO users (id, email, name, password) VALUES (gen_random_uuid()::text, $1, $2, crypt($3, gen_salt('bf', 12)))
ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, password = EXCLUDED.password, updated_at = now()
WHERE users.password IS DISTINCT FROM crypt($3, users.password) OR users.name IS DISTINCT FROM EXCLUDED.name
"""
# The role is set on every run: an account made OWNER in the UI goes back to what the file says.
SQL_MEMBERSHIP = """
INSERT INTO organization_memberships (id, org_id, user_id, role)
SELECT gen_random_uuid()::text, $1, id, $3::"Role" FROM users WHERE email = $2
ON CONFLICT (org_id, user_id) DO UPDATE SET role = EXCLUDED.role, updated_at = now()
"""


def fast_hash(secret_key: str, salt: str) -> str:
    """SHA-256 of the key followed by the hex SHA-256 of the salt: createShaHash in Langfuse."""
    salt_hash = hashlib.sha256(salt.encode()).hexdigest()
    return hashlib.sha256((secret_key + salt_hash).encode()).hexdigest()


def display_key(secret_key: str) -> str:
    return f"{secret_key[:6]}...{secret_key[-4:]}"


def required_env(name: str, what: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        sys.exit(f"{what}: set {name} in .env")
    return value


def api(method: str, path: str, keys: tuple[str, str], body: dict | None = None) -> tuple[int, dict]:
    """Call Langfuse's public API with the API keys of a project."""
    token = base64.b64encode(":".join(keys).encode()).decode()
    request = urllib.request.Request(
        LANGFUSE_URL + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def match_pattern(alias: str, model: str) -> str:
    """Regex of the model names a trace of this alias can carry.

    Most traces carry the alias, but a streamed call carries the model behind it ("qwen2.5:1.5b"), and a call served
    by a fallback carries it with its provider ("ollama_chat/qwen2.5:0.5b"): each must get the alias's price.
    """
    provider, _, name = model.rpartition("/")
    prefix = f"({re.escape(provider)}/)?" if provider else ""
    return f"(?i)^({re.escape(alias)}|{prefix}{re.escape(name)})$"


def alias_prices() -> list[dict]:
    """Langfuse model definitions of the aliases, with their internal prices from config/litellm.yaml."""
    with open(LITELLM_CONFIG) as file:
        models = yaml.safe_load(file)["model_list"]
    served = [model["litellm_params"]["model"].rpartition("/")[2] for model in models]
    if len(set(served)) < len(served):
        # A trace that carries the model name could not tell which alias, hence which price, it belongs to.
        sys.exit(f"{LITELLM_CONFIG}: two aliases serve the same model, Langfuse could not price their traces")
    return [
        {
            "modelName": model["model_name"],
            "matchPattern": match_pattern(model["model_name"], model["litellm_params"]["model"]),
            "unit": "TOKENS",
            "inputPrice": model["litellm_params"].get("input_cost_per_token", 0),
            "outputPrice": model["litellm_params"].get("output_cost_per_token", 0),
        }
        for model in models
    ]


def ensure_prices(project: str, keys: tuple[str, str]) -> None:
    """Create the price of each alias in the project, or replace it when config/litellm.yaml changed."""
    existing, page = {}, 1
    while True:
        status, answer = api("GET", f"/api/public/models?page={page}&limit=100", keys)
        if status != 200:
            sys.exit(f"langfuse project {project}: listing the models failed with HTTP {status}: {answer}")
        for model in answer["data"]:
            if not model["isLangfuseManaged"]:
                existing[model["modelName"]] = model
        if page >= answer["meta"]["totalPages"]:
            break
        page += 1

    for price in alias_prices():
        current = existing.get(price["modelName"])
        if current and all(current[field] == price[field] for field in ("matchPattern", "inputPrice", "outputPrice")):
            continue
        # A model definition cannot be edited through the API: replace it.
        if current:
            api("DELETE", f"/api/public/models/{current['id']}", keys)
        status, answer = api("POST", "/api/public/models", keys, price)
        if status != 200:
            sys.exit(f"langfuse project {project}: price of {price['modelName']} failed with HTTP {status}: {answer}")
    print(f"langfuse project {project}: prices of the aliases up to date")


async def ensure_teams(teams: list[dict]) -> None:
    salt = required_env("LANGFUSE_SALT", "langfuse")
    admin_email = required_env("LANGFUSE_ADMIN_EMAIL", "langfuse").lower()
    db = Prisma(datasource={"url": required_env("LANGFUSE_DATABASE_URL", "langfuse")})
    await db.connect()
    try:
        await db.execute_raw(SQL_EXTENSION)
        for team in teams:
            team_id, settings = team["team_id"], team["langfuse"]
            secret_key = required_env(settings["secret_key_env"], f"team {team_id}")
            if not settings["public_key"].startswith("pk-lf-") or not secret_key.startswith("sk-lf-"):
                sys.exit(f"team {team_id}: Langfuse keys must start with 'pk-lf-' and 'sk-lf-'")
            password = required_env(settings["viewer_password_env"], f"team {team_id}")

            # Organization and project share the team id; the platform admin owns every team's organization.
            await db.execute_raw(SQL_ORG, team_id, team["team_alias"])
            await db.execute_raw(SQL_PROJECT, team_id, team_id, team["team_alias"])
            await db.execute_raw(
                SQL_API_KEY, settings["public_key"], secret_key, fast_hash(secret_key, salt), display_key(secret_key),
                team_id,
            )
            await db.execute_raw(SQL_MEMBERSHIP, team_id, admin_email, "OWNER")
            viewer = settings["viewer_email"].lower()
            await db.execute_raw(SQL_USER, viewer, f"{team['team_alias']} lead", password)
            await db.execute_raw(SQL_MEMBERSHIP, team_id, viewer, "VIEWER")
            print(f"langfuse organization {team_id}: project, API keys and viewer {viewer} up to date")
    finally:
        await db.disconnect()


def main(teams: list[dict]) -> None:
    """Set up Langfuse for the teams, then the prices of the aliases in their projects and in Gateway."""
    teams = [team for team in teams if "langfuse" in team]
    asyncio.run(ensure_teams(teams))

    projects = {"gateway": (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])}
    for team in teams:
        projects[team["team_id"]] = (team["langfuse"]["public_key"], os.environ[team["langfuse"]["secret_key_env"]])
    for project, keys in projects.items():
        ensure_prices(project, keys)
