"""FrAddressRecognizer: French postal addresses."""

import pytest


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Le bailleur est domicilié 12 rue Victor Hugo à Nantes.", "12 rue Victor Hugo"),
        ("Adresse : 12 rue de la Paix, 75002 Paris", "12 rue de la Paix, 75002 Paris"),
        ("Envoyez le courrier au 3 bis avenue du Général de Gaulle 69003 Lyon.", "3 bis avenue du Général de Gaulle 69003 Lyon"),
        ("Le logement sis 45, boulevard Haussmann est loué meublé.", "45, boulevard Haussmann"),
        ("Rendez-vous 8 place de l'Église.", "8 place de l'Église"),
        ("Il habite 150 Chemin des Vignes, 13100 Aix-en-Provence.", "150 Chemin des Vignes, 13100 Aix-en-Provence"),
        ("Siège : 1 allée Jean Jaurès 31000 Toulouse Cedex 9", "1 allée Jean Jaurès 31000 Toulouse Cedex 9"),
        ("Local situé 27 quai Saint-Nicolas.", "27 quai Saint-Nicolas"),
        ("Code postal 33000 Bordeaux", "33000 Bordeaux"),
        ("Domicile : 5 impasse des Lilas, 97400 Saint-Denis", "5 impasse des Lilas, 97400 Saint-Denis"),
        # Address block of a letter: postcode and city on the next line.
        ("Jean Martin\n24 chemin Voltaire\n63000 Clermont-Ferrand\n\nObjet", "24 chemin Voltaire\n63000 Clermont-Ferrand"),
        ("156, quai du Général Traore,\n80000 Amiens", "156, quai du Général Traore,\n80000 Amiens"),
    ],
)
def test_finds_an_address(detect, text, expected):
    assert expected in detect("FR_ADDRESS", text)


@pytest.mark.parametrize(
    "text",
    [
        "Hamilton a pris la tête au tour 42 à Monaco.",
        "La rue était calme ce soir-là.",  # street type, no number
        "Il a couru 12 rues sans s'arrêter.",  # "rues" is not a street type here
        "En 2024 Paris a accueilli les Jeux olympiques.",  # year then city: not a postcode
        "Le loyer passe de 850 à 900 euros au 1er janvier.",
        "Il reste 3 places de parking.",  # lowercase word after the street type
    ],
)
def test_ignores_what_is_not_an_address(detect, text):
    assert detect("FR_ADDRESS", text) == []
