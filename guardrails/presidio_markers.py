"""LiteLLM's Presidio guardrail, with two fixes to its numbered markers (docs/adr/015-presidio-marker-fixes.md).

With output_parse_pii, LiteLLM replaces each detection with a numbered marker such as <PERSON_1> and puts the
original values back into the answer. Its numbering has two bugs, open upstream in version 1.83.14:

1. Detections of different types can overlap (an address and the city inside it, an IBAN and its country code as a
   LOCATION). LiteLLM replaces each one at its original position, which splices markers into each other:
   "<FR_ADDRESS_2>ON_4>". BerriAI/litellm#42130.
2. Each message is numbered from 1, so two people named in two messages both become <PERSON_1>, and the answer
   gets the wrong name back. BerriAI/litellm#31959.

config/litellm.yaml loads the class with `guardrail: presidio_markers.PresidioStableMarkers`, from the directory of
the config file, where compose.yaml mounts this file. Everything else is LiteLLM's own Presidio guardrail.
"""

from litellm.proxy.guardrails.guardrail_hooks.presidio import _OPTIONAL_PresidioPIIMasking


def merge_overlaps(results: list[dict]) -> list[dict]:
    """Return one detection per group of overlapping ones, sorted by position.

    The merged span covers the whole group, so no character of any detection stays in clear. Its entity type is
    that of the longest detection of the group, then of the highest score, then the last in alphabetical order:
    the Analyzer returns results in no fixed order, and a tax number that also passes the card checksum must get
    the same marker type on every run.
    """
    groups: list[list[dict]] = []
    for result in sorted(results, key=lambda r: r["start"]):
        if groups and result["start"] < max(r["end"] for r in groups[-1]):
            groups[-1].append(result)
        else:
            groups.append([result])

    merged = []
    for group in groups:
        main = max(group, key=lambda r: (r["end"] - r["start"], r["score"], r["entity_type"]))
        start = min(r["start"] for r in group)
        end = max(r["end"] for r in group)
        merged.append(main | {"start": start, "end": end})
    return merged


def replace_with_markers(text: str, results: list[dict], tokens: dict[str, str]) -> str:
    """Replace each detection, which must not overlap, with its marker.

    tokens maps the markers of the request to their original values; new ones are added to it. Numbers run across
    the whole request, and a value seen before gets its marker back.
    """
    markers = {value: marker for marker, value in tokens.items()}
    spans = []
    for result in results:
        value = text[result["start"] : result["end"]]
        if value not in markers:
            marker = f"<{result['entity_type']}_{len(tokens) + 1}>"
            tokens[marker] = value
            markers[value] = marker
        spans.append((result["start"], result["end"], markers[value]))
    # From the end, so earlier positions stay valid.
    for start, end, marker in reversed(spans):
        text = text[:start] + marker + text[end:]
    return text


class PresidioStableMarkers(_OPTIONAL_PresidioPIIMasking):
    """Presidio guardrail whose markers never overlap and stay unique across the messages of a request."""

    def _finalize_presidio_anonymize_numbered_tokens(
        self,
        text: str,
        analyze_results: list[dict],
        request_data: dict | None,
        masked_entity_count: dict[str, int],
    ) -> str:
        # Same storage as LiteLLM: the post-call hook reads the markers from request_data["metadata"]["pii_tokens"].
        if request_data is None:
            request_data = {}
        if not request_data.get("metadata"):
            request_data["metadata"] = {}
        tokens = request_data["metadata"].setdefault("pii_tokens", {})

        results = merge_overlaps(analyze_results)
        for result in results:
            entity_type = result["entity_type"]
            masked_entity_count[entity_type] = masked_entity_count.get(entity_type, 0) + 1
        return replace_with_markers(text, results, tokens)
