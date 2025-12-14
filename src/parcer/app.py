from __future__ import annotations

import argparse
import asyncio
import logging

from .config import load_settings
from .di import build_container
from .logging import configure_logging
from .runtime import run

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="parcer", description="parcer arbitrage bot scaffold")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config file (default: PARCER_CONFIG or ./config.yml)",
    )

    args = parser.parse_args(argv)

    configure_logging()

    settings = load_settings(args.config)
    container = build_container(settings)

    logger.info("parcer booting")
    asyncio.run(run(container))
    logger.info("parcer exit")

    return 0
