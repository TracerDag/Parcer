from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import load_settings
from .di import build_container
from .logging import configure_logging
from .runtime import run

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Main entry point supporting both CLI commands and background bot mode.

    - `parcer` or `parcer bot`: run background bot mode
    - `parcer <typer-subcommand>`: run CLI mode (e.g. `parcer trade open ...`)
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        return _run_bot_mode([])

    if argv[0] == "bot":
        return _run_bot_mode(argv[1:])

    return _run_cli_mode(argv)


def _run_bot_mode(argv: list[str]) -> int:
    """Run in background bot mode."""
    parser = argparse.ArgumentParser(
        prog="parcer bot", description="Run arbitrage bot in background"
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config file (default: PARCER_CONFIG or ./config.yml)",
    )

    args = parser.parse_args(argv)
    configure_logging(Path("logs"))

    settings = load_settings(args.config)

    from .exchanges.init import create_exchange_clients_from_settings

    exchange_clients = create_exchange_clients_from_settings(settings)
    container = build_container(settings, exchange_clients)

    logger.info("parcer bot booting")
    asyncio.run(run(container))
    logger.info("parcer bot exit")

    return 0


def _run_cli_mode(argv: list[str]) -> int:
    """Run in CLI mode using Typer."""
    try:
        # Configure basic logging for CLI
        configure_logging(Path("logs"))
        
        # Import CLI app here to avoid circular import
        from .cli import app as typer_app, run_cli
        run_cli(argv)
        return 0
    except SystemExit as e:
        return e.code if e.code else 0
    except Exception as e:
        logger.error("CLI error: %s", e, exc_info=True)
        return 1
