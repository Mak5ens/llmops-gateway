"""The fixes applied to LiteLLM when the gateway's image is built (docker/litellm/patch_litellm.py), checked against
the LiteLLM version pinned in pyproject.toml, which follows the image.

If a test says a patch no longer applies after a LiteLLM bump, look at the new code: the bug may be fixed upstream,
and the patch can go.
"""

import subprocess
import sys
import types
from pathlib import Path

import litellm
import pytest
from patch_litellm import PATCHES, Patch, apply

PACKAGE = Path(litellm.__file__).parent

# Prices a TEI rerank deployment the way the router does for the `rerank` alias, then prints its cost.
RERANK_COST = """
import litellm
from litellm.cost_calculator import rerank_cost
litellm.register_model({"deployment-id": {"input_cost_per_query": 0.001}})
print(rerank_cost(model="deployment-id", custom_llm_provider="huggingface", billed_units={"search_units": 1})[0])
"""


def rerank_cost(patched: bool) -> float:
    """Run in a fresh interpreter: the patched source is executed over litellm.utils there, never here."""
    patch = ""
    if patched:
        patch = (
            "import litellm.utils, pathlib\n"
            "from patch_litellm import PATCHES, apply\n"
            "path = pathlib.Path(litellm.utils.__file__)\n"
            "source = apply(path.read_text(), PATCHES[0])\n"
            "exec(compile(source, str(path), 'exec'), litellm.utils.__dict__)\n"
        )
    result = subprocess.run(
        [sys.executable, "-c", patch + RERANK_COST],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).parents[2] / "docker" / "litellm",
    )
    return float(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("patch", PATCHES, ids=lambda patch: patch.file)
def test_every_patch_applies_once_to_the_pinned_litellm(patch: Patch) -> None:
    patched = apply((PACKAGE / patch.file).read_text(), patch)
    assert patch.new in patched


def test_a_patch_that_does_not_match_fails() -> None:
    with pytest.raises(ValueError, match="appears 0 times"):
        apply("unrelated source", PATCHES[0])


def test_a_tei_rerank_deployment_keeps_its_price() -> None:
    assert rerank_cost(patched=True) == pytest.approx(0.001)


def test_the_bug_is_still_there_upstream() -> None:
    # When this fails, LiteLLM prices TEI deployments on its own: remove the patch.
    assert rerank_cost(patched=False) == 0.0


def tei_rerank_body(patched: bool) -> dict:
    """The body LiteLLM posts to TEI, from the transformation module run in a namespace of its own."""
    path = PACKAGE / PATCHES[1].file
    source = path.read_text()
    if patched:
        source = apply(source, PATCHES[1])
    module = types.ModuleType("tei_rerank_transformation")
    module.__package__ = "litellm.llms.huggingface.rerank"  # for its relative imports
    exec(compile(source, str(path), "exec"), module.__dict__)
    config = module.HuggingFaceRerankConfig()
    return config.transform_rerank_request(
        model="tei", optional_rerank_params={"query": "q", "texts": ["a"]}, headers={}
    )


def test_a_tei_rerank_request_lets_the_server_truncate() -> None:
    assert "truncate" not in tei_rerank_body(patched=True)


def test_the_truncate_bug_is_still_there_upstream() -> None:
    # When this fails, LiteLLM no longer forces `truncate: false` on TEI: remove the patch.
    assert tei_rerank_body(patched=False)["truncate"] is False
