"""FrNirRecognizer: French social security numbers, kept only when the key is right."""

import pytest

VALID = [
    ("Mon numéro de sécurité sociale est le 1 85 05 78 006 084 91.", "1 85 05 78 006 084 91"),
    ("NIR : 185057800608491", "185057800608491"),
    ("Assurée n° 2 95 10 99 126 111 93", "2 95 10 99 126 111 93"),
    # Born in Corsica: 2A and 2B count as 19 and 18 in the key.
    ("Carte vitale 1 55 01 2A 001 234 83", "1 55 01 2A 001 234 83"),
    ("Carte vitale 2 69 06 2B 123 456 34", "2 69 06 2B 123 456 34"),
    # Month unknown at registration: 20 to 42, or 50 to 99.
    ("NIR 1 63 29 91 230 010 85", "1 63 29 91 230 010 85"),
    ("NIR 2 88 55 75 056 123 12", "2 88 55 75 056 123 12"),
    # Temporary numbers start with 3, 4, 7 or 8.
    ("Numéro provisoire 3 85 05 78 006 084 88", "3 85 05 78 006 084 88"),
    ("NIR 7 99 12 31 001 002 39", "7 99 12 31 001 002 39"),
    # Overseas department 971.
    ("né en Guadeloupe, NIR 2 88 07 97 101 123 16", "2 88 07 97 101 123 16"),
]


@pytest.mark.parametrize(("text", "expected"), VALID)
def test_finds_a_valid_nir(detect, text, expected):
    assert detect("FR_NIR", text) == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "Mon numéro est le 1 85 05 78 006 084 92.",  # wrong key
        "NIR 5 85 05 78 006 084 91",  # no sex digit 5
        "NIR 1 85 13 78 006 084 91",  # no month 13
        "NIR 1 85 05 78 006 084",  # key missing
        "Commande 185057800608491234",  # longer number
        "Montant total : 123 456 789 012 345 €",
    ],
)
def test_ignores_what_is_not_a_valid_nir(detect, text):
    assert detect("FR_NIR", text) == []
