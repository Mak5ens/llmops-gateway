"""What the pinned LiteLLM lets through to the models of config/litellm.yaml. No network: the Router is built from the
configuration, and LiteLLM is asked which OpenAI parameters it would send.

chat-pro's model is missing from LiteLLM's model map, which took it for a model without tool calling: `tools` and
`tool_choice` were removed from every request, without an error since drop_params was on (LAB-199).
"""

import litellm
from litellm import Router
from test_provider_budget import CONFIG, deployments

TOOL_PARAMS = {"tools", "tool_choice"}


def test_chat_pro_keeps_tools() -> None:
    Router(model_list=deployments("chat-pro"))  # registers the model_info of the configuration
    model = deployments("chat-pro")[0]["litellm_params"]["model"]
    provider, name = model.split("/", 1)

    assert TOOL_PARAMS <= set(litellm.get_supported_openai_params(model=name, custom_llm_provider=provider))


def test_a_parameter_the_model_does_not_take_is_refused() -> None:
    assert CONFIG["litellm_settings"]["drop_params"] is False
