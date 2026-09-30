"""UrlOutsideEmailRecognizer: URLs, but not the domain of an e-mail address."""


def test_ignores_the_domain_of_an_email(detect):
    assert detect("URL", "Écrivez-moi à marie.dupont@example.fr.") == []


def test_still_finds_a_url(detect):
    assert detect("URL", "Le contrat est sur https://example.fr/bail et sur example.org.") == [
        "https://example.fr/bail",
        "example.org",
    ]
