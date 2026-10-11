"""Entry point: `python -m llmops_worker`, configured from the environment (README of worker/)."""

import asyncio
import logging
import sys

from . import tracing
from .worker import Settings, Worker, team_keys


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # Each job logs its own line; the HTTP clients' lines would double them.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    tracing.setup()
    try:
        code = asyncio.run(Worker(Settings.from_environment(), team_keys()).serve())
    finally:
        tracing.shutdown()
    sys.exit(code)


if __name__ == "__main__":
    main()
