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


def test_analyzer_does_not_report_the_email_domain_as_a_url():
    assert not [result for result in analyze(TEXT, "fr") if result["entity_type"] == "URL"]


LEASE = (
    "Entre les soussignés : Mme Sophie Leroy, numéro de sécurité sociale 2 88 55 75 056 123 12, "
    "domiciliée 12 rue de la Paix, 75002 Paris, joignable au 06 12 34 56 78 ou à sophie.leroy@example.fr, "
    "numéro fiscal 30 23 217 600 053, IBAN FR76 3000 6000 0112 3456 7890 189."
)


def test_analyzer_finds_french_identifiers_in_a_lease():
    entities = found(LEASE, analyze(LEASE, "fr"))

    assert {
        ("FR_NIR", "2 88 55 75 056 123 12"),
        ("FR_ADDRESS", "12 rue de la Paix, 75002 Paris"),
        ("PHONE_NUMBER", "06 12 34 56 78"),
        ("EMAIL_ADDRESS", "sophie.leroy@example.fr"),
        ("FR_FISCAL_NUMBER", "30 23 217 600 053"),
        ("IBAN_CODE", "FR76 3000 6000 0112 3456 7890 189"),
    } <= entities


def test_context_words_raise_the_score():
    scores = {result["entity_type"]: result["score"] for result in analyze(LEASE, "fr")}

    # Base scores are 0.6 for an address and 0.4 for a phone number; "domiciliée" and "joignable" raise them.
    assert scores["FR_ADDRESS"] > 0.6
    assert scores["PHONE_NUMBER"] > 0.4


# Pattern-based entities: only a name or a place from the spaCy model may show up in ordinary numbers.
IDENTIFIERS = {"FR_NIR", "FR_FISCAL_NUMBER", "FR_ADDRESS", "PHONE_NUMBER", "IBAN_CODE", "CREDIT_CARD", "IP_ADDRESS"}


def test_analyzer_finds_no_identifier_in_ordinary_numbers():
    text = (
        "Au tour 42, Hamilton a signé un 1:23.456 et creusé l'écart à 12,5 secondes, 18 tours avant la fin sur 58. "
        "Le loyer de 1 250 € augmente de 3,5 % au 1er janvier 2025 ; dépôt de garantie 2 500 euros, 45 m², "
        "3 pièces au 2e étage. Chiffre d'affaires 2024 : 12 345 678 €. Commande 20240315-0042 du 15/03/2024."
    )

    assert not {entity for entity, _ in found(text, analyze(text, "fr"))} & IDENTIFIERS


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
