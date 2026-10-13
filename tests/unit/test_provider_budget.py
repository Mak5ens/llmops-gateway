"""The Scaleway budget of config/litellm.yaml on the router of the pinned LiteLLM: once the cap is spent, chat-pro is
refused, and the local aliases still answer. Mock responses, no network: the cap is lowered to the cost of one call.
"""

import asyncio
from pathlib import Path

import pytest
import yaml
from litellm import Router

CONFIG = yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "litellm.yaml").read_text())
MESSAGES = [{"role": "user", "content": "Bonjour"}]


def deployments(*aliases: str) -> list[dict]:
    """The aliases' deployments as configured, with their environment references replaced by test values."""
    models = []
    for model in CONFIG["model_list"]:
        if model["model_name"] in aliases:
            params = {
                key: "http://test.invalid" if str(value).startswith("os.environ/") else value
                for key, value in model["litellm_params"].items()
            }
            models.append({**model, "litellm_params": params})
    return models


def test_the_cap_is_on_scaleway_only() -> None:
    budget = CONFIG["router_settings"]["provider_budget_config"]

    assert budget == {"scaleway": {"budget_limit": 5, "time_period": "30d"}}
    providers = {model["litellm_params"]["model"].split("/")[0] for model in deployments("chat-pro")}
    assert providers == {"scaleway"}
    assert "chat-pro" not in str(CONFIG["router_settings"]["fallbacks"])  # refused, never silently replaced


def test_over_the_cap_chat_pro_is_refused_and_local_aliases_answer() -> None:
    async def calls() -> None:
        # Built in the event loop: the budget limiter starts a background task.
        router = Router(
            model_list=deployments("chat-pro", "chat-small"),
            provider_budget_config={"scaleway": {"budget_limit": 1e-9, "time_period": "30d"}},
        )
        await router.acompletion(model="chat-pro", messages=MESSAGES, mock_response="Salut !")
        await asyncio.sleep(0.5)  # the spend is counted by a success callback, after the answer
        with pytest.raises(Exception, match="(?i)budget"):
            await router.acompletion(model="chat-pro", messages=MESSAGES, mock_response="Salut !")
        answer = await router.acompletion(model="chat-small", messages=MESSAGES, mock_response="Salut !")
        assert answer.choices[0].message.content == "Salut !"

    asyncio.run(calls())
