"""FrPersonRecognizer: French names that spaCy misses without context.

Scores matter here: the guardrail masks from 0.4, and a first name alone scores 0.3 until a context word raises it
inside the Analyzer (tests/integration/test_presidio.py covers that part).
"""

import pytest
from pii_recognizers import FrPersonRecognizer

THRESHOLD = 0.4


@pytest.fixture(scope="module")
def names(registry):
    (recognizer,) = [r for r in registry.get_recognizers(language="fr", entities=["PERSON"]) if isinstance(r, FrPersonRecognizer)]

    def run(text: str) -> dict[str, float]:
        return {text[r.start : r.end]: r.score for r in recognizer.analyze(text, ["PERSON"], None)}

    return run


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Lucy Petit\n34 bis, avenue Chrétien, 75011 Paris", "Lucy Petit"),  # letter header
        ("Cordialement,\nÉmilie Georges", "Émilie Georges"),  # signature
        ("Bien à vous,\nMarine", "Marine"),  # first name alone on the signature line
        ("M. Lucas Salmon\n154, rue Gambetta", "Lucas Salmon"),
        ("Mme Victoire Berthelot", "Victoire Berthelot"),
        ("Bonjour Docteur Camus,", "Camus"),
        ("Nom : Buisson\nPrénom : Sébastien", "Buisson"),
        ("Notre gestionnaire, Victoire Marie, reste à votre disposition.", "Victoire Marie"),
        ("Je soussigné(e) Marc Renaud, demeurant au 3 rue Voltaire", "Marc Renaud"),
        ("Le dossier de Jean-Pierre Da Costa est complet.", "Jean-Pierre Da Costa"),
        ("La gérante, Emmanuelle du Lefèvre, a signé.", "Emmanuelle du Lefèvre"),
    ],
)
def test_finds_a_name(names, text, expected):
    assert names(text).get(expected, 0) >= THRESHOLD


@pytest.mark.parametrize(
    ("text", "first_name"),
    [
        ("Salut Anaïs, c'est Franck.", "Anaïs"),
        ("Un rendez-vous pour mon fils Nicolas la semaine prochaine.", "Nicolas"),
        ("Pierre de taille et Rose des vents.", "Pierre"),
    ],
)
def test_a_first_name_alone_waits_for_context(names, text, first_name):
    # Found, but below the threshold: the Analyzer's context words (salut, fils...) decide.
    assert 0 < names(text)[first_name] < THRESHOLD


@pytest.mark.parametrize(
    "text",
    [
        "Agence Horizon Gestion\nSIRET 527 593 828 07063",  # company header, no first name
        "Madame, Monsieur,",
        "Monsieur le Directeur,",
        "Service des impôts des particuliers de Paris",
        "FORMULAIRE D'ADHÉSION",
        "France Travail a validé votre inscription.",  # excluded from the first names
        "Objet : relance loyer impayé",
    ],
)
def test_ignores_what_is_not_a_name(names, text):
    assert all(score < THRESHOLD for score in names(text).values()), names(text)
