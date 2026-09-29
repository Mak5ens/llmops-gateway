"""FrFiscalNumberRecognizer: French tax numbers, kept only when the last 3 digits check."""

import pytest


@pytest.mark.parametrize(
    "number",
    [
        "30 23 217 600 053",
        "3023217600053",
        "01 23 456 789 211",
        "12 34 567 890 066",
        "29 99 999 999 248",
        "31 00 000 000 104",
        "15 10 000 000 110",
        "20 12 345 678 084",
        "33 33 333 333 106",
        "07 00 000 000 007",
    ],
)
def test_finds_a_valid_fiscal_number(detect, number):
    assert detect("FR_FISCAL_NUMBER", f"Numéro fiscal : {number}.") == [number]


@pytest.mark.parametrize(
    "text",
    [
        "Numéro fiscal : 30 23 217 600 054.",  # wrong check digits
        "Numéro fiscal : 40 23 217 600 053.",  # cannot start with 4
        "Numéro fiscal : 30 23 217 600.",  # too short
        "Référence 30232176000530",  # longer number
        "Chiffre d'affaires : 1 234 567 890 123 €.",
    ],
)
def test_ignores_what_is_not_a_valid_fiscal_number(detect, text):
    assert detect("FR_FISCAL_NUMBER", text) == []
