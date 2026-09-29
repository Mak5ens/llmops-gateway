"""French postal address."""

from presidio_analyzer import Pattern, PatternRecognizer

# Presidio compiles patterns with IGNORECASE (global_regex_flags), so words that must start with a capital
# letter turn it off locally with (?-i:...).
_NUMBER = r"\d{1,4}(?: ?(?:bis|ter|quater|[a-d])\b)?,?"
_STREET_TYPE = (
    r"(?:rue|avenue|av\.|boulevard|bd|place|chemin|allée|impasse|quai|route|cours|square|passage|faubourg"
    r"|chaussée|voie|sentier|hameau|lieu-dit|résidence|promenade|esplanade|cité|villa|parvis|rond-point)(?![\w-])"
)
_LINK = r"(?:de la|de l['’]|des|du|de|d['’]|la|le|les|l['’]|aux|au|et|sur|sous|en)"
_WORD = r"(?-i:[A-ZÀ-ÖØ-Þ0-9][\w'’-]*)"
_STREET_NAME = rf"(?:{_LINK} ?)?{_WORD}(?: (?:{_LINK} ?)?{_WORD})*"
_POSTCODE = r"(?:0[1-9]|[1-8]\d|9[0-5]|97|98)\d{3}"
_CITY = rf"{_WORD}(?:[ -](?:(?:sur|sous|en|lès|les|la|le|de|du|des|d['’])[ -])?{_WORD})*(?: cedex(?: \d{{1,2}})?)?"


class FrAddressRecognizer(PatternRecognizer):
    """Recognize a French address: number, street type and name, then optionally postcode and city.

    `12 rue de la Paix, 75002 Paris` is one result. A postcode followed by a city is also a result on its
    own, with a low score that the context words (domicilié, adresse...) raise.
    There is no checksum: street types and capitalized names are what keep the false positives out.
    """

    PATTERNS = [
        Pattern("street address", rf"\b{_NUMBER} ?{_STREET_TYPE} {_STREET_NAME}(?:,? {_POSTCODE} {_CITY})?", 0.6),
        Pattern("postcode and city", rf"\b{_POSTCODE} {_CITY}", 0.3),
    ]
    CONTEXT = ["adresse", "domicil", "demeur", "habit", "postal", "situé", "résid"]

    def __init__(self, supported_language: str = "fr", context: list[str] | None = None, name: str | None = None):
        super().__init__(
            supported_entity="FR_ADDRESS",
            patterns=self.PATTERNS,
            context=context or self.CONTEXT,
            supported_language=supported_language,
            name=name,
        )
