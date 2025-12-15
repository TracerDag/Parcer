"""Scenario B: Futures vs Futures arbitrage strategy."""

from __future__ import annotations

import logging

from parcer.exchanges.protocol import ExchangeClient
from parcer.exchanges.normalization import check_symbol_mismatch

from parcer.orders.manager import OrderManager
from parcer.orders.position import Position

from .spread_engine import SpreadDetectionEngine

logger = logging.getLogger(__name__)


class ScenarioBStrategy:
    """Futures vs Futures arbitrage strategy.

    Entry: Long cheap perpetual + short expensive when spread >= 7%
    Exit: Close when spread drops below 1%
    """

    def __init__(
        self,
        spread_engine: SpreadDetectionEngine,
        order_manager: OrderManager,
    ) -> None:
        self.spread_engine = spread_engine
        self.order_manager = order_manager
        self.current_position: Position | None = None

    async def check_entry(
        self,
        exchange_a_client: ExchangeClient,
        exchange_b_client: ExchangeClient,
        symbol_a: str,
        symbol_b: str,
        entry_threshold: float,
        entry_quantity: float,
    ) -> Position | None:
        """Check for entry signal and create position if threshold met.

        Args:
            exchange_a_client: First futures exchange client
            exchange_b_client: Second futures exchange client
            symbol_a: Symbol on first exchange
            symbol_b: Symbol on second exchange
            entry_threshold: Entry threshold (e.g., 0.07 for 7%)
            entry_quantity: Quantity for each leg

        Returns:
            Position if entry signal triggered, None otherwise
        """
        if self.current_position is not None:
            logger.debug("Position already open, skipping entry check")
            return None

        try:
            price_a = self.spread_engine.get_price(
                exchange_a_client.name, symbol_a
            )
            price_b = self.spread_engine.get_price(
                exchange_b_client.name, symbol_b
            )

            if price_a is None or price_b is None:
                logger.debug(
                    "Missing prices: %s=%s %s=%s",
                    exchange_a_client.name,
                    price_a,
                    exchange_b_client.name,
                    price_b,
                )
                return None

            spread_calc = self.spread_engine.detect_scenario_b_spread(
                price_a, price_b, exchange_a_client.name, exchange_b_client.name
            )
            spread = spread_calc.spread

            logger.debug(
                "Scenario B spread check: %.4f%% (threshold: %.4f%%)",
                spread * 100,
                entry_threshold * 100,
            )

            if not self.spread_engine.check_entry_condition(
                spread, entry_threshold, scenario="b"
            ):
                return None

            check_symbol_mismatch(symbol_a, symbol_b)

            logger.info(
                "Scenario B entry signal: %.4f%% spread between %s and %s",
                spread * 100,
                exchange_a_client.name,
                exchange_b_client.name,
            )

            long_exchange = (
                exchange_a_client
                if price_a < price_b
                else exchange_b_client
            )
            short_exchange = (
                exchange_b_client
                if price_a < price_b
                else exchange_a_client
            )
            long_symbol = symbol_a if price_a < price_b else symbol_b
            short_symbol = symbol_b if price_a < price_b else symbol_a

            position = self.order_manager.create_position(
                symbol_a=long_symbol,
                exchange_a=long_exchange.name,
                symbol_b=short_symbol,
                exchange_b=short_exchange.name,
                scenario="b",
                leg_a_side="buy",
                leg_a_quantity=entry_quantity,
                leg_b_side="sell",
                leg_b_quantity=entry_quantity,
            )

            success = await self.order_manager.entry_order(
                position,
                long_exchange,
                short_exchange,
                price_hint_a=spread_calc.price_discount,
                price_hint_b=spread_calc.price_premium,
            )

            if success:
                self.current_position = position
                return position
            return None

        except Exception as e:
            logger.error("Error checking entry condition: %s", e, exc_info=True)
            return None

    async def check_exit(
        self,
        exchange_a_client: ExchangeClient,
        exchange_b_client: ExchangeClient,
        symbol_a: str,
        symbol_b: str,
        exit_threshold: float,
    ) -> bool:
        """Check for exit signal and close position if threshold met.

        Args:
            exchange_a_client: First futures exchange client
            exchange_b_client: Second futures exchange client
            symbol_a: Symbol on first exchange
            symbol_b: Symbol on second exchange
            exit_threshold: Exit threshold (e.g., 0.01 for 1%)

        Returns:
            True if position was closed
        """
        if self.current_position is None:
            return False

        if not self.current_position.is_open:
            return False

        try:
            position = self.current_position
            price_a = self.spread_engine.get_price(
                exchange_a_client.name, symbol_a
            )
            price_b = self.spread_engine.get_price(
                exchange_b_client.name, symbol_b
            )

            if price_a is None or price_b is None:
                logger.debug("Missing prices for exit check")
                return False

            spread_calc = self.spread_engine.detect_scenario_b_spread(
                price_a, price_b, exchange_a_client.name, exchange_b_client.name
            )
            spread = spread_calc.spread

            logger.debug(
                "Scenario B exit check: spread %.4f%% (exit threshold: %.4f%%)",
                spread * 100,
                exit_threshold * 100,
            )

            if not self.spread_engine.check_exit_condition(
                spread, exit_threshold, scenario="b"
            ):
                return False

            logger.info(
                "Scenario B exit signal: spread narrowed to %.4f%%",
                spread * 100,
            )

            success = await self.order_manager.exit_order(
                position, exchange_a_client, exchange_b_client
            )

            if success:
                self.current_position = None
                return True

            return False

        except Exception as e:
            logger.error("Error checking exit condition: %s", e, exc_info=True)
            return False

    def get_current_position(self) -> Position | None:
        """Get currently open position."""
        return self.current_position
