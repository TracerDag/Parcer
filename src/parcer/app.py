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
    """Main entry point supporting both CLI commands and background bot mode."""
    parser = argparse.ArgumentParser(prog="parcer", description="parcer arbitrage bot")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["bot", None],
        help="Command to run (default: bot for background mode)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config file (default: PARCER_CONFIG or ./config.yml)",
    )

    # Parse known args to see if it's a CLI command
    args, remaining = parser.parse_known_args(argv)
    
    # If no command specified or command is "bot", run background mode
    if not args.command or args.command == "bot":
        return _run_bot_mode(remaining)
    
    # Otherwise, run CLI mode
    return _run_cli_mode(argv)


def _run_bot_mode(argv: list[str]) -> int:
    """Run in background bot mode (original behavior)."""
    parser = argparse.ArgumentParser(prog="parcer bot", description="Run arbitrage bot in background")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config file (default: PARCER_CONFIG or ./config.yml)",
    )
    
    args = parser.parse_args(argv)
    configure_logging(Path("logs"))

    settings = load_settings(args.config)
    container = build_container(settings)

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
