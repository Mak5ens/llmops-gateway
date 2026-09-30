"""French person names that the spaCy model misses without context."""

from pathlib import Path

import regex as re
from presidio_analyzer import AnalysisExplanation, LocalRecognizer, RecognizerResult

FIRST_NAMES_FILE = Path(__file__).with_name("data") / "fr_first_names.txt"

# A capitalized word: "Anaïs", "Jean-Pierre", "N'Golo". All-caps words (SIRET, FORMULAIRE) are left out.
_WORD = r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+(?:['’-][A-ZÀ-ÖØ-Þa-zà-öø-ÿ][a-zà-öø-ÿ]+)*"
# Capitalized words in a row, with the particles of French surnames between them: "Emmanuelle du Lefèvre".
_RUN = re.compile(rf"(?<![\w'’-]){_WORD}(?: (?:(?:de la|de|du|des|d['’]) ?)?{_WORD})*")
_WORD_RE = re.compile(_WORD)
TITLES = {"Mme", "Mlle", "Madame", "Mademoiselle", "Monsieur", "Docteur", "Dr", "Maître", "Me", "Professeur", "Pr"}
# "M." is not a capitalized word, so it is looked for just before the run.
_TITLE_BEFORE = re.compile(r"(?<![\w.])M\. $")
_FIELD_BEFORE = re.compile(r"(?i:\b(?:nom|prénom|nom de famille|nom d'usage|nom de naissance)) ?: ?$")


class FrPersonRecognizer(LocalRecognizer):
    """Recognize French person names from their shape and INSEE's list of first names.

    - after a title or a form field: "M. Lucas Salmon", "Docteur Camus", "Nom : Buisson";
    - alone on a line, starting with a known first name: the header or the signature of a letter;
    - a known first name followed by capitalized words: "Hortense Rodriguez";
    - a known first name alone ("Salut Anaïs", "mon fils Nicolas"): low score, raised by the context words.
    Presidio's spaCy recognizer still finds the rest; overlapping results are merged downstream.
    """

    CONTEXT = [
        "salut", "coucou", "bonjour", "bonsoir", "cher", "fils", "fille", "mari", "femme", "épouse", "époux",
        "frère", "sœur", "enfant", "ami", "collègue", "gestionnaire", "manager", "assuré", "salarié", "soussign",
        "prénom", "signé", "cordialement",
    ]
    SCORE_STRONG = 0.85
    SCORE_FULL_NAME = 0.6
    SCORE_FIRST_NAME_ALONE = 0.3

    def __init__(self, supported_language: str = "fr", context: list[str] | None = None, name: str | None = None):
        super().__init__(
            supported_entities=["PERSON"],
            name=name,
            supported_language=supported_language,
            context=context or self.CONTEXT,
        )

    def load(self) -> None:
        lines = FIRST_NAMES_FILE.read_text(encoding="utf-8").splitlines()
        self.first_names = frozenset(line for line in lines if line and not line.startswith("#"))

    def analyze(self, text: str, entities: list[str], nlp_artifacts=None) -> list[RecognizerResult]:
        results = []
        for run in _RUN.finditer(text):
            words = [(run.start() + w.start(), w.group()) for w in _WORD_RE.finditer(run.group())]
            before = text[: run.start()]
            titled = bool(_TITLE_BEFORE.search(before) or _FIELD_BEFORE.search(before))
            # A run can start with other capitalized words: "Bonjour Docteur Étienne", "Salut Anaïs".
            # The name starts after the last title, or else at the first known first name.
            titles = [i for i, (_, word) in enumerate(words) if word in TITLES]
            if titles:
                words, titled = words[titles[-1] + 1 :], True
            elif not titled:
                first = next((i for i, (_, word) in enumerate(words) if word in self.first_names), None)
                if first is None:
                    continue
                words = words[first:]
            if not words:
                continue
            start, end = words[0][0], run.end()
            score, rule = self._score(text, start, end, [word for _, word in words], titled)
            results.append(self._result(start, end, score, rule))
        return results

    def _score(self, text: str, start: int, end: int, words: list[str], titled: bool) -> tuple[float, str]:
        if titled:
            return self.SCORE_STRONG, "after a title or a name field"
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        line = text[line_start : line_end if line_end != -1 else len(text)]
        if line.strip(" ,.;!") == text[start:end]:
            return self.SCORE_STRONG, "name alone on its line"
        if len(words) > 1:
            return self.SCORE_FULL_NAME, "first name and surname"
        return self.SCORE_FIRST_NAME_ALONE, "first name alone"

    def _result(self, start: int, end: int, score: float, rule: str) -> RecognizerResult:
        # The Analyzer's context enhancer needs both the explanation, which it updates, and the metadata, which
        # tells it whose context words apply.
        return RecognizerResult(
            entity_type="PERSON",
            start=start,
            end=end,
            score=score,
            analysis_explanation=AnalysisExplanation(
                recognizer=self.name, original_score=score, textual_explanation=f"FrPersonRecognizer: {rule}"
            ),
            recognition_metadata={
                RecognizerResult.RECOGNIZER_NAME_KEY: self.name,
                RecognizerResult.RECOGNIZER_IDENTIFIER_KEY: self.id,
            },
        )
