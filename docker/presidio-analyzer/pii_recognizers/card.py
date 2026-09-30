"""Payment card numbers, Mastercard 2-series included."""

from presidio_analyzer import Pattern
from presidio_analyzer.predefined_recognizers import CreditCardRecognizer


class CardRecognizer(CreditCardRecognizer):
    """Presidio's credit card recognizer, with the Mastercard numbers that start with 2221 to 2720.

    Mastercard has issued them since 2017, and the stock pattern only accepts cards starting with 1, 3, 4, 5 or 6.
    The Luhn check of the parent class still drops any number whose check digit is wrong.
    """

    PATTERNS = [
        Pattern(
            "Credit cards, Mastercard 2-series included (weak)",
            r"\b(?!1\d{12}(?!\d))((4\d{3})|(5[0-5]\d{2})|(6\d{3})|(1\d{3})|(3\d{3})"
            r"|(222[1-9]|22[3-9]\d|2[3-6]\d{2}|27[01]\d|2720))[- ]?(\d{3,4})[- ]?(\d{3,4})[- ]?(\d{3,5})\b",
            0.3,
        ),
    ]
    CONTEXT = [*CreditCardRecognizer.CONTEXT, "carte", "bancaire", "cb", "paiement", "débit"]

    def __init__(self, supported_language: str = "en", context: list[str] | None = None, name: str | None = None):
        super().__init__(
            patterns=self.PATTERNS, context=context or self.CONTEXT, supported_language=supported_language, name=name
        )
