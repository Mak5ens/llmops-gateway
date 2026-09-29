"""Entry point of the Analyzer: the official app, with the recognizers of pii_recognizers defined first."""

import pii_recognizers  # noqa: F401  (defines the classes that config/presidio/recognizers.yaml names)
from app import create_app

__all__ = ["create_app"]
