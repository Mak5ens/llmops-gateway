"""French phone numbers."""

from presidio_analyzer.predefined_recognizers import PhoneRecognizer


class FrPhoneRecognizer(PhoneRecognizer):
    """Presidio's phone recognizer (python-phonenumbers) for French numbers, with French context words.

    The stock one does not look for French numbers, and the YAML loader drops its `supported_regions`
    argument, hence a subclass rather than configuration. Numbers written with +33 or 0033 are found
    whatever the region, so it also covers French numbers in an English text.
    """

    CONTEXT = ["téléphon", "tél", "portable", "mobile", "fixe", "appel", "joign", "joindre"]

    def __init__(self, supported_language: str = "fr", context: list[str] | None = None, name: str | None = None):
        super().__init__(
            context=context or self.CONTEXT, supported_language=supported_language, supported_regions=("FR",), name=name
        )
