"""Run the recognizers as configured in config/presidio/recognizers.yaml, without the stack or a spaCy model.

Pattern recognizers need no NLP artifacts, so these tests check patterns and check digits in a few seconds.
Context words, which raise scores inside the Analyzer, are covered by tests/integration/test_presidio.py.
"""

from collections.abc import Callable
from pathlib import Path

import pii_recognizers  # noqa: F401  (defines the classes the configuration names)
import pytest
from presidio_analyzer.recognizer_registry import RecognizerRegistry, RecognizerRegistryProvider

CONFIG = Path(__file__).resolve().parents[2] / "config" / "presidio" / "recognizers.yaml"


@pytest.fixture(scope="session")
def registry() -> RecognizerRegistry:
    return RecognizerRegistryProvider(conf_file=str(CONFIG)).create_recognizer_registry()


@pytest.fixture(scope="session")
def detect(registry: RecognizerRegistry) -> Callable[..., list[str]]:
    """Return the spans of `text` that the configured recognizers of `entity` report, in order."""

    def run(entity: str, text: str, language: str = "fr") -> list[str]:
        spans = set()
        for recognizer in registry.get_recognizers(language=language, entities=[entity]):
            for result in recognizer.analyze(text, [entity], None):
                if result.entity_type == entity:
                    spans.add((result.start, result.end))
        return [text[start:end] for start, end in sorted(spans)]

    return run
