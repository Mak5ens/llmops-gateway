"""French tax number (numéro fiscal de référence, or SPI)."""

from presidio_analyzer import Pattern, PatternRecognizer


class FrFiscalNumberRecognizer(PatternRecognizer):
    """Recognize the 13-digit number of a French taxpayer, written on tax notices as `30 23 217 600 053`.

    It starts with 0, 1, 2 or 3, and its last 3 digits are the first 10 mod 511, which rejects
    all but one in 511 random 13-digit numbers.
    """

    PATTERNS = [Pattern("SPI", r"\b[0-3]\d ?\d{2} ?\d{3} ?\d{3} ?\d{3}\b", 0.3)]
    CONTEXT = ["fiscal", "impôt", "imposition", "spi", "revenus"]

    def __init__(self, supported_language: str = "fr", context: list[str] | None = None, name: str | None = None):
        super().__init__(
            supported_entity="FR_FISCAL_NUMBER",
            patterns=self.PATTERNS,
            context=context or self.CONTEXT,
            supported_language=supported_language,
            name=name,
        )

    def validate_result(self, pattern_text: str) -> bool:
        number = pattern_text.replace(" ", "")
        return int(number[:10]) % 511 == int(number[10:])
