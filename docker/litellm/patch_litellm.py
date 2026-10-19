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
    Patch(
        file="llms/huggingface/rerank/transformation.py",
        # transform_rerank_request: every request to TEI said `truncate: false`, which overrides the server's
        # --auto-truncate. A (question, passage) pair longer than the model reads (512 tokens on the CPU reranker)
        # then failed the whole call with a 422 (LAB-211). With the patch, the server decides.
        old=(
            '            "raw_scores": False,\n'
            '            "truncate": False,\n'
            '            "truncation_direction": "Right",\n'
        ),
        new=(
            '            "raw_scores": False,\n'
            "            # llmops-gateway patch (docker/litellm/patch_litellm.py): TEI's --auto-truncate decides.\n"
            '            "truncation_direction": "Right",\n'
        ),
        why="TEI rerank requests refuse a pair longer than the model reads, whatever the server's --auto-truncate",
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
