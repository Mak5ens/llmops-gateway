"""URL recognizer that leaves e-mail addresses to the e-mail recognizer."""

from presidio_analyzer import RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts
from presidio_analyzer.predefined_recognizers import UrlRecognizer


class UrlOutsideEmailRecognizer(UrlRecognizer):
    """Presidio's URL recognizer, minus the domain of an e-mail address.

    The stock one also returns `example.fr` inside `marie@example.fr`, next to the EMAIL_ADDRESS result.
    """

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: NlpArtifacts | None = None, regex_flags: int | None = None
    ) -> list[RecognizerResult]:
        results = super().analyze(text, entities, nlp_artifacts, regex_flags)
        return [result for result in results if result.start == 0 or text[result.start - 1] != "@"]
