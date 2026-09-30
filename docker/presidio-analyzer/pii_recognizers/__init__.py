"""Custom Presidio recognizers for French personal data.

Importing this package defines the classes. Presidio's registry finds recognizers among the subclasses of
EntityRecognizer, so config/presidio/recognizers.yaml can then list them by class name, as `type: predefined`.
"""

from pii_recognizers.card import CardRecognizer
from pii_recognizers.fr_address import FrAddressRecognizer
from pii_recognizers.fr_fiscal_number import FrFiscalNumberRecognizer
from pii_recognizers.fr_nir import FrNirRecognizer
from pii_recognizers.fr_person import FrPersonRecognizer
from pii_recognizers.fr_phone import FrPhoneRecognizer
from pii_recognizers.url import UrlOutsideEmailRecognizer

__all__ = [
    "CardRecognizer",
    "FrAddressRecognizer",
    "FrFiscalNumberRecognizer",
    "FrNirRecognizer",
    "FrPersonRecognizer",
    "FrPhoneRecognizer",
    "UrlOutsideEmailRecognizer",
]
