"""IbanRecognizer as configured: French IBANs, kept only when the check digits (mod 97) are right."""

import pytest


@pytest.mark.parametrize(
    "iban",
    [
        "FR76 3000 6000 0112 3456 7890 189",
        "FR7630006000011234567890189",
        "FR14 2004 1010 0505 0001 3M02 606",
        "FR1420041010050500013M02606",
        "FR76 1010 7001 0112 3456 7890 129",
        "FR76 3000 4000 0312 3456 7890 143",
    ],
)
def test_finds_a_valid_french_iban(detect, iban):
    assert detect("IBAN_CODE", f"Merci de faire le virement sur l'IBAN {iban}.") == [iban]


@pytest.mark.parametrize(
    "text",
    [
        "IBAN FR76 3000 6000 0112 3456 7890 188",  # wrong check digits
        "IBAN FR76 1450 8000 4012 3456 7890 123",  # wrong check digits
        "IBAN FR76 3000 6000 0112 3456 7890",  # too short
        "Référence FR-2024-000123 du dossier.",
    ],
)
def test_ignores_what_is_not_a_valid_iban(detect, text):
    assert detect("IBAN_CODE", text) == []
