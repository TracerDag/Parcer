"""Spread detection and calculation engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PriceType(Enum):
    """Price type for spread calculation."""

    SPOT = "spot"
    MARK = "mark"


@dataclass
class PricePoint:
    """Single price observation."""

    price: float
    price_type: PriceType
    exchange: str
    symbol: str
    timestamp: int | None = None


@dataclass
class SpreadCalculation:
    """Result of spread calculation."""

    spread: float
    premium_exchange: str
    discount_exchange: str
    price_premium: float
    price_discount: float


class SpreadDetectionEngine:
    """Detects and calculates spreads between price pairs."""

    def __init__(self) -> None:
        self.price_cache: dict[str, PricePoint] = {}

    def update_price(
        self,
        exchange: str,
        symbol: str,
        price: float,
        price_type: PriceType = PriceType.MARK,
        timestamp: int | None = None,
    ) -> None:
        """Update cached price for a symbol on an exchange."""
        key = self._make_key(exchange, symbol)
        self.price_cache[key] = PricePoint(
            price=price,
            price_type=price_type,
            exchange=exchange,
            symbol=symbol,
            timestamp=timestamp,
        )

    def get_price(
        self, exchange: str, symbol: str
    ) -> float | None:
        """Get latest cached price."""
        key = self._make_key(exchange, symbol)
        point = self.price_cache.get(key)
        return point.price if point else None

    def calculate_spread(
        self,
        price_a: float,
        price_b: float,
        premium_base: bool = True,
    ) -> float:
        """Calculate spread between two prices.

        Args:
            price_a: First price
            price_b: Second price
            premium_base: If True, spread = (price_a - price_b) / price_b
                         If False, spread = (price_b - price_a) / price_a

        Returns:
            Spread as decimal (e.g., 0.05 = 5%)
        """
        if price_b == 0 or price_a == 0:
            return 0.0

        if premium_base:
            return (price_a - price_b) / price_b
        else:
            return (price_b - price_a) / price_a

    def detect_scenario_a_spread(
        self,
        futures_price: float,
        spot_price: float,
    ) -> SpreadCalculation:
        """Detect spread for scenario A (spot vs futures).

        Scenario A: Long futures (premium) + short spot (discount)
        We want futures to have premium over spot.

        Args:
            futures_price: Futures/perpetual price
            spot_price: Spot market price

        Returns:
            SpreadCalculation with spread and premium info
        """
        spread = self.calculate_spread(futures_price, spot_price, premium_base=True)
        premium_exchange = "futures" if spread > 0 else "spot"
        discount_exchange = "spot" if spread > 0 else "futures"

        return SpreadCalculation(
            spread=spread,
            premium_exchange=premium_exchange,
            discount_exchange=discount_exchange,
            price_premium=max(futures_price, spot_price),
            price_discount=min(futures_price, spot_price),
        )

    def detect_scenario_b_spread(
        self,
        price_a: float,
        price_b: float,
        exchange_a: str = "A",
        exchange_b: str = "B",
    ) -> SpreadCalculation:
        """Detect spread for scenario B (futures vs futures).

        Scenario B: Long cheap + short expensive
        Spread = (expensive - cheap) / cheap

        Args:
            price_a: Price on first exchange
            price_b: Price on second exchange
            exchange_a: Name of first exchange
            exchange_b: Name of second exchange

        Returns:
            SpreadCalculation with spread and premium info
        """
        if price_a < price_b:
            spread = (price_b - price_a) / price_a
            premium_exchange = exchange_b
            discount_exchange = exchange_a
            price_premium = price_b
            price_discount = price_a
        else:
            spread = (price_a - price_b) / price_b
            premium_exchange = exchange_a
            discount_exchange = exchange_b
            price_premium = price_a
            price_discount = price_b

        return SpreadCalculation(
            spread=spread,
            premium_exchange=premium_exchange,
            discount_exchange=discount_exchange,
            price_premium=price_premium,
            price_discount=price_discount,
        )

    def check_entry_condition(
        self,
        spread: float,
        entry_threshold: float,
        scenario: str = "a",
    ) -> bool:
        """Check if spread meets entry threshold.

        Args:
            spread: Current spread
            entry_threshold: Threshold for entry (decimal, e.g., 0.05 = 5%)
            scenario: Strategy scenario ("a" or "b")

        Returns:
            True if spread meets entry condition
        """
        if scenario == "a":
            return abs(spread) >= entry_threshold
        else:
            return abs(spread) >= entry_threshold

    def check_exit_condition(
        self,
        spread: float,
        exit_threshold: float,
        scenario: str = "a",
    ) -> bool:
        """Check if spread has decreased to exit threshold.

        Args:
            spread: Current spread
            exit_threshold: Threshold for exit (decimal, e.g., 0.01 = 1%)
            scenario: Strategy scenario ("a" or "b")

        Returns:
            True if spread should trigger exit
        """
        if scenario == "a":
            return abs(spread) <= exit_threshold
        else:
            return abs(spread) <= exit_threshold

    def _make_key(self, exchange: str, symbol: str) -> str:
        return f"{exchange}:{symbol}"
