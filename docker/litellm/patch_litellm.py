"""Fixes applied to LiteLLM's source when the gateway's image is built, until LiteLLM ships them.

Run by docker/litellm/Dockerfile. Each patch must match the installed source exactly once, or the build fails:
a LiteLLM bump that changes the code breaks the build instead of silently dropping the fix.
`tests/unit/test_litellm_patches.py` checks that every patch still applies to the pinned LiteLLM version.
"""

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Patch:
    file: str  # relative to the litellm package
    old: str
    new: str
    why: str


PATCHES = [
    Patch(
        file="utils.py",
        # _get_model_info_helper: any `huggingface/` model was described as a free chat model, which ignored the
        # price of the deployment. The `rerank` alias (TEI, LiteLLM's huggingface provider) then cost $0, so its
        # calls escaped the team budgets (ADR-014). With the patch, a model priced in the cost map keeps its price.
        # Upstream: https://github.com/BerriAI/litellm/issues/45975
        old=(
            "                        e,\n"
            "                    )\n"
            "\n"
            '        if custom_llm_provider == "huggingface":\n'
        ),
        new=(
            "                        e,\n"
            "                    )\n"
            "\n"
            "        # llmops-gateway patch (docker/litellm/patch_litellm.py): keep the price of a priced deployment.\n"
            '        if custom_llm_provider == "huggingface" and model not in litellm.model_cost:\n'
        ),
        why="Hugging Face (TEI) rerank deployments are priced at $0 whatever their configured price",
    ),
]


def apply(source: str, patch: Patch) -> str:
    count = source.count(patch.old)
    if count != 1:
        raise ValueError(f"{patch.file}: the code to patch appears {count} times, expected once ({patch.why})")
    return source.replace(patch.old, patch.new)


def main(package: Path) -> None:
    for patch in PATCHES:
        path = package / patch.file
        path.write_text(apply(path.read_text(), patch))
        print(f"patched {path}: {patch.why}")


if __name__ == "__main__":
    import litellm

    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(litellm.__file__).parent)
