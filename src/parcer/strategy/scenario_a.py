"""Scenario A: Spot vs Futures arbitrage strategy."""

from __future__ import annotations

import logging
from typing import Any

from parcer.exchanges.protocol import ExchangeClient
from parcer.exchanges.normalization import check_symbol_mismatch

from parcer.orders.manager import OrderManager
from parcer.orders.position import Position

from .spread_engine import SpreadDetectionEngine, PriceType

logger = logging.getLogger(__name__)


class ScenarioAStrategy:
    """Spot vs Futures arbitrage strategy.

    Entry: Long futures + short spot when futures premium exceeds threshold
    Exit: Close when spread narrows below exit threshold
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
        futures_client: ExchangeClient,
        spot_client: ExchangeClient,
        futures_symbol: str,
        spot_symbol: str,
        entry_threshold: float,
        entry_quantity: float,
    ) -> Position | None:
        """Check for entry signal and create position if threshold met.

        Args:
            futures_client: Futures/perpetual exchange client
            spot_client: Spot market exchange client
            futures_symbol: Symbol on futures exchange
            spot_symbol: Symbol on spot exchange
            entry_threshold: Entry threshold (e.g., 0.05 for 5%)
            entry_quantity: Quantity for each leg

        Returns:
            Position if entry signal triggered, None otherwise
        """
        if self.current_position is not None:
            logger.debug("Position already open, skipping entry check")
            return None

        try:
            futures_price = self.spread_engine.get_price(
                futures_client.name, futures_symbol
            )
            spot_price = self.spread_engine.get_price(
                spot_client.name, spot_symbol
            )

            if futures_price is None or spot_price is None:
                logger.debug(
                    "Missing prices: futures=%s spot=%s",
                    futures_price,
                    spot_price,
                )
                return None

            spread_calc = self.spread_engine.detect_scenario_a_spread(
                futures_price, spot_price
            )
            spread = spread_calc.spread

            logger.debug(
                "Scenario A spread check: %s %.4f%% (threshold: %.4f%%)",
                "PREMIUM" if spread > 0 else "DISCOUNT",
                abs(spread) * 100,
                entry_threshold * 100,
            )

            if not self.spread_engine.check_entry_condition(
                spread, entry_threshold, scenario="a"
            ):
                return None

            check_symbol_mismatch(futures_symbol, spot_symbol)

            logger.info(
                "Scenario A entry signal: %.4f%% premium on futures",
                spread * 100,
            )

            position = self.order_manager.create_position(
                symbol_a=futures_symbol,
                exchange_a=futures_client.name,
                symbol_b=spot_symbol,
                exchange_b=spot_client.name,
                scenario="a",
                leg_a_side="buy",
                leg_a_quantity=entry_quantity,
                leg_b_side="sell",
                leg_b_quantity=entry_quantity,
            )

            success = await self.order_manager.entry_order(
                position,
                futures_client,
                spot_client,
                price_hint_a=futures_price,
                price_hint_b=spot_price,
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
        futures_client: ExchangeClient,
        spot_client: ExchangeClient,
        exit_threshold: float,
    ) -> bool:
        """Check for exit signal and close position if threshold met.

        Args:
            futures_client: Futures/perpetual exchange client
            spot_client: Spot market exchange client
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
            futures_price = self.spread_engine.get_price(
                futures_client.name, position.symbol_a
            )
            spot_price = self.spread_engine.get_price(
                spot_client.name, position.symbol_b
            )

            if futures_price is None or spot_price is None:
                logger.debug("Missing prices for exit check")
                return False

            spread_calc = self.spread_engine.detect_scenario_a_spread(
                futures_price, spot_price
            )
            spread = spread_calc.spread

            logger.debug(
                "Scenario A exit check: spread %.4f%% (exit threshold: %.4f%%)",
                abs(spread) * 100,
                exit_threshold * 100,
            )

            if not self.spread_engine.check_exit_condition(
                spread, exit_threshold, scenario="a"
            ):
                return False

            logger.info(
                "Scenario A exit signal: spread narrowed to %.4f%%",
                abs(spread) * 100,
            )

            success = await self.order_manager.exit_order(
                position, futures_client, spot_client
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
