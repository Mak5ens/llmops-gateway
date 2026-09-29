"""Presidio called directly: the Analyzer finds personal data in French, the Anonymizer replaces it.

The gateway does not call Presidio yet (LAB-115); these tests check the services it will rely on.
"""

import httpx
from helpers import PRESIDIO_ANALYZER_URL, PRESIDIO_ANONYMIZER_URL

TEXT = "Bonjour, je suis Marie Dupont et j'habite à Lyon. Écrivez-moi à marie.dupont@example.fr."


def analyze(text: str, language: str) -> list[dict]:
    response = httpx.post(f"{PRESIDIO_ANALYZER_URL}/analyze", json={"text": text, "language": language}, timeout=30)
    response.raise_for_status()
    return response.json()


def found(text: str, results: list[dict]) -> set[tuple[str, str]]:
    return {(result["entity_type"], text[result["start"] : result["end"]]) for result in results}


def test_analyzer_finds_person_place_and_email_in_french():
    entities = found(TEXT, analyze(TEXT, "fr"))

    assert ("PERSON", "Marie Dupont") in entities
    assert ("LOCATION", "Lyon") in entities
    assert ("EMAIL_ADDRESS", "marie.dupont@example.fr") in entities


def test_analyzer_still_supports_english():
    text = "John Smith lives in London."

    entities = found(text, analyze(text, "en"))

    assert {("PERSON", "John Smith"), ("LOCATION", "London")} <= entities


def test_anonymizer_replaces_what_the_analyzer_found():
    results = [r for r in analyze(TEXT, "fr") if r["entity_type"] in {"PERSON", "LOCATION"}]

    response = httpx.post(
        f"{PRESIDIO_ANONYMIZER_URL}/anonymize", json={"text": TEXT, "analyzer_results": results}, timeout=30
    )
    response.raise_for_status()

    anonymized = response.json()["text"]
    assert "Marie Dupont" not in anonymized and "Lyon" not in anonymized
    assert "<PERSON>" in anonymized and "<LOCATION>" in anonymized
