"""Numbered markers of the pii-fr guardrail (guardrails/presidio_markers.py), without Presidio or a model."""

from presidio_markers import PresidioStableMarkers, merge_overlaps

# Detections returned by the Analyzer for this text, overlaps included (captured from the running stack).
TEXT = "Je suis Marie Dupont, j habite au 12 rue de la Paix, 75002 Paris. Mon IBAN est FR76 3000 6000 0112 3456 7890 189."
DETECTIONS = [
    {"entity_type": "PERSON", "start": 8, "end": 20, "score": 0.85},
    {"entity_type": "FR_ADDRESS", "start": 34, "end": 64, "score": 0.95},
    {"entity_type": "LOCATION", "start": 37, "end": 51, "score": 0.85},
    {"entity_type": "LOCATION", "start": 59, "end": 64, "score": 0.85},
    {"entity_type": "IBAN_CODE", "start": 79, "end": 112, "score": 1.0},
    {"entity_type": "LOCATION", "start": 79, "end": 83, "score": 0.85},
]


def detection(entity_type: str, start: int, end: int, score: float = 0.85) -> dict:
    return {"entity_type": entity_type, "start": start, "end": end, "score": score}


def guardrail() -> PresidioStableMarkers:
    # mock_testing skips the check of the Presidio URLs; only the marker numbering is exercised.
    return PresidioStableMarkers(guardrail_name="pii-fr", event_hook="pre_call", output_parse_pii=True, mock_testing=True)


def mask(text: str, detections: list[dict], request: dict) -> str:
    return guardrail()._finalize_presidio_anonymize_numbered_tokens(text, detections, request, {})


def test_a_detection_inside_another_one_is_absorbed():
    assert merge_overlaps([detection("FR_ADDRESS", 0, 30, 0.6), detection("LOCATION", 25, 30)]) == [
        detection("FR_ADDRESS", 0, 30, 0.6)
    ]


def test_partly_overlapping_detections_become_their_union():
    # The longest one gives the type; no character of the shorter one stays in clear.
    assert merge_overlaps([detection("PERSON", 5, 12), detection("FR_ADDRESS", 0, 10, 0.6)]) == [
        detection("FR_ADDRESS", 0, 12, 0.6)
    ]


def test_same_span_keeps_the_highest_score():
    assert merge_overlaps([detection("LOCATION", 0, 4, 0.85), detection("IBAN_CODE", 0, 4, 1.0)]) == [
        detection("IBAN_CODE", 0, 4, 1.0)
    ]


def test_a_tie_gives_the_same_type_in_any_order():
    # A 13-digit tax number starting with 3 can also pass the card checksum: same span, same score.
    card, tax = detection("CREDIT_CARD", 0, 13, 1.0), detection("FR_FISCAL_NUMBER", 0, 13, 1.0)
    assert merge_overlaps([card, tax]) == merge_overlaps([tax, card]) == [tax]


def test_adjacent_detections_stay_apart():
    merged = merge_overlaps([detection("PERSON", 5, 10), detection("PERSON", 0, 5)])
    assert merged == [detection("PERSON", 0, 5), detection("PERSON", 5, 10)]


def test_overlapping_detections_give_clean_markers():
    request: dict = {}
    assert mask(TEXT, DETECTIONS, request) == (
        "Je suis <PERSON_1>, j habite au <FR_ADDRESS_2>. Mon IBAN est <IBAN_CODE_3>."
    )
    assert request["metadata"]["pii_tokens"] == {
        "<PERSON_1>": "Marie Dupont",
        "<FR_ADDRESS_2>": "12 rue de la Paix, 75002 Paris",
        "<IBAN_CODE_3>": "FR76 3000 6000 0112 3456 7890 189",
    }


def test_numbers_run_across_the_messages_of_a_request():
    request: dict = {}
    first = mask("Le bailleur est Jean Martin.", [detection("PERSON", 16, 27)], request)
    second = mask("La locataire est Marie Dupont.", [detection("PERSON", 17, 29)], request)
    assert (first, second) == ("Le bailleur est <PERSON_1>.", "La locataire est <PERSON_2>.")


def test_a_value_keeps_its_marker():
    request: dict = {}
    mask("Le bailleur est Jean Martin.", [detection("PERSON", 16, 27)], request)
    again = mask("Jean Martin et Marie Dupont", [detection("PERSON", 0, 11), detection("PERSON", 15, 27)], request)
    assert again == "<PERSON_1> et <PERSON_2>"


def test_markers_are_stored_where_the_answer_is_unmasked():
    # LiteLLM's post-call hook reads request["metadata"]["pii_tokens"] to put the values back.
    request: dict = {"metadata": {"user_api_key_team_id": "baux"}}
    mask("Je suis Marie Dupont.", [detection("PERSON", 8, 20)], request)
    answer = "Bonjour <PERSON_1>, votre dossier est prêt."
    tokens = request["metadata"]["pii_tokens"]
    assert PresidioStableMarkers._unmask_pii_text(answer, tokens) == "Bonjour Marie Dupont, votre dossier est prêt."
    assert request["metadata"]["user_api_key_team_id"] == "baux"


def test_ten_markers_do_not_collide():
    # <PERSON_1> must not match inside <PERSON_10> when the answer is unmasked.
    request: dict = {}
    names = [f"Nom{i:02d}" for i in range(1, 11)]
    text = " ".join(names)
    detections = [detection("PERSON", i * 6, i * 6 + 5) for i in range(10)]
    masked = mask(text, detections, request)
    assert PresidioStableMarkers._unmask_pii_text(masked, request["metadata"]["pii_tokens"]) == text


def test_the_masked_entity_count_follows_the_merged_detections():
    count: dict[str, int] = {}
    guardrail()._finalize_presidio_anonymize_numbered_tokens(TEXT, DETECTIONS, {}, count)
    assert count == {"PERSON": 1, "FR_ADDRESS": 1, "IBAN_CODE": 1}
