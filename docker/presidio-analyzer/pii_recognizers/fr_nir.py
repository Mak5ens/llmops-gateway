"""French social security number (NIR, numéro de sécurité sociale)."""

from presidio_analyzer import Pattern, PatternRecognizer


class FrNirRecognizer(PatternRecognizer):
    """Recognize a NIR by its structure, then keep it only if its 2-digit key is right.

    15 characters, often written `1 85 05 78 006 084 91`:
    sex (1, 2, or 3, 4, 7, 8 for temporary numbers), year, month (01-12, or 20-42 and 50-99 when unknown),
    birth place (department and town, 2A or 2B in Corsica), order number, key.
    The key is 97 - (the first 13 digits mod 97), with 2A read as 19 and 2B as 18.
    """

    PATTERNS = [
        Pattern(
            "NIR",
            r"\b[1-478] ?\d{2} ?(?:0[1-9]|1[0-2]|[2-3]\d|4[0-2]|[5-9]\d) ?(?:\d{2}|2[AB]) ?\d{3} ?\d{3} ?\d{2}\b",
            0.3,
        ),
    ]
    # Presidio matches each context word as a substring of the lemmas of the 5 words before the match, so
    # these are single words or stems.
    CONTEXT = ["sécurité", "sociale", "sécu", "nir", "insee", "vitale", "assuré"]

    def __init__(self, supported_language: str = "fr", context: list[str] | None = None, name: str | None = None):
        super().__init__(
            supported_entity="FR_NIR",
            patterns=self.PATTERNS,
            context=context or self.CONTEXT,
            supported_language=supported_language,
            name=name,
        )

    def validate_result(self, pattern_text: str) -> bool:
        nir = pattern_text.replace(" ", "").upper()
        digits = nir[:13].replace("2A", "19").replace("2B", "18")
        return 97 - int(digits) % 97 == int(nir[13:])
