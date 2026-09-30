"""CardRecognizer: payment cards, Mastercard 2-series included, checked with Luhn."""

import pytest


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Débité sur ma carte 2504947677811852.", "2504947677811852"),
        ("Carte 2288 6305 6008 4678 refusée.", "2288 6305 6008 4678"),
        ("Carte 2705 6170 4998 9739, expire en 2028.", "2705 6170 4998 9739"),
        ("CB 2720 2012 7716 8687", "2720 2012 7716 8687"),
        ("Carte 2221 0000 0000 0009", "2221 0000 0000 0009"),
        # The ranges the stock recognizer already covered still work.
        ("Visa 4111 1111 1111 1111", "4111 1111 1111 1111"),
        ("Mastercard 5555-5555-5555-4444", "5555-5555-5555-4444"),
        ("Amex 378282246310005", "378282246310005"),
    ],
)
def test_finds_a_card(detect, text, expected):
    assert detect("CREDIT_CARD", text) == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "Carte 2504 9476 7781 1853 refusée.",  # 2-series, wrong Luhn digit
        "Carte 2220 0000 0000 0000",  # just below the 2-series range
        "Carte 2721 0000 0000 0007",  # just above it
        "SIRET 527 593 828 07063",
    ],
)
def test_ignores_what_is_not_a_card(detect, text):
    assert detect("CREDIT_CARD", text) == []
