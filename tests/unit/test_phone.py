"""PhoneRecognizer as configured for French: region FR through the phonenumbers library."""

import pytest


@pytest.mark.parametrize(
    "number",
    [
        "06 12 34 56 78",
        "0612345678",
        "06.12.34.56.78",
        "06-12-34-56-78",
        "07 81 23 45 67",
        "01 42 68 53 00",
        "+33 6 12 34 56 78",
        "+33612345678",
        "+33 (0)1 42 68 53 00",
        "0033 1 42 68 53 00",
    ],
)
def test_finds_a_french_phone_number(detect, number):
    assert detect("PHONE_NUMBER", f"Vous pouvez me joindre au {number} demain.") == [number]


def test_finds_a_french_number_in_an_english_text(detect):
    assert detect("PHONE_NUMBER", "Call me on +33 6 12 34 56 78.", language="en") == ["+33 6 12 34 56 78"]


@pytest.mark.parametrize(
    "text",
    [
        "Le loyer est de 1 250 euros.",
        "Le montant est de 12 345 678 €.",
        "Tour 42, meilleur temps 1:23.456.",
        "Le bail commence le 12/03/2024.",
        "Budget 2024 2025 2026 2027",
        "06 12 34 56",  # too short
    ],
)
def test_ignores_what_is_not_a_phone_number(detect, text):
    assert detect("PHONE_NUMBER", text) == []
