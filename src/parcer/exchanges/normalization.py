"""Symbol normalization utilities for exchange symbols."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def normalize_symbol(symbol: str, format: str = "unified") -> str:
    """Normalize a symbol to a standard format.

    Converts various symbol formats to a unified format:
    - BTCUSDT -> BTCUSDT (unchanged if unified format)
    - BTC-USDT -> BTCUSDT
    - BTC/USDT -> BTCUSDT

    Args:
        symbol: Symbol in any format
        format: Target format ('unified' for BTCUSDT, 'hyphen' for BTC-USDT, 'slash' for BTC/USDT)

    Returns:
        Normalized symbol
    """
    if not symbol:
        return symbol

    symbol = symbol.strip()

    # First normalize to unified format
    unified = symbol.replace("-", "").replace("/", "").replace(" ", "").upper()

    if format == "unified":
        return unified
    elif format == "hyphen":
        base, quote = extract_base_symbol(symbol)
        if base and quote:
            return f"{base}-{quote}"
        return unified
    elif format == "slash":
        base, quote = extract_base_symbol(symbol)
        if base and quote:
            return f"{base}/{quote}"
        return unified
    else:
        return unified


def extract_base_symbol(symbol: str) -> tuple[str, str]:
    """Extract base and quote currency from a symbol.

    Handles various formats:
    - BTCUSDT -> (BTC, USDT)
    - BTC-USDT -> (BTC, USDT)
    - BTC/USDT -> (BTC, USDT)
    - BTC -> (BTC, '')

    Args:
        symbol: Symbol in any format

    Returns:
        Tuple of (base, quote) currencies
    """
    if not symbol:
        return "", ""

    symbol = symbol.strip().upper()

    if "-" in symbol:
        parts = symbol.split("-")
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()

    if "/" in symbol:
        parts = symbol.split("/")
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()

    usdt_stablecoins = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "USDD"}
    for stablecoin in sorted(usdt_stablecoins, key=len, reverse=True):
        if symbol.endswith(stablecoin):
            base = symbol[: -len(stablecoin)]
            if base:
                return base, stablecoin

    return symbol, ""


def check_symbol_mismatch(
    expected: str,
    actual: str,
    logger_func: Any = None,
) -> bool:
    """Check if two symbols represent the same trading pair.

    Logs a warning if they don't match.

    Args:
        expected: Expected symbol
        actual: Actual symbol
        logger_func: Logger function (defaults to logging.warning)

    Returns:
        True if symbols match, False otherwise
    """
    if logger_func is None:
        logger_func = logger.warning

    expected_normalized = normalize_symbol(expected)
    actual_normalized = normalize_symbol(actual)

    if expected_normalized != actual_normalized:
        logger_func(
            f"Symbol mismatch: expected {expected} ({expected_normalized}), "
            f"got {actual} ({actual_normalized})"
        )
        return False

    return True
