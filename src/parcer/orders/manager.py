"""Order management for arbitrage strategies."""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..history import TradeHistory

from ..exchanges.protocol import ExchangeClient, Order

from .position import Position, PositionStatus

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order status."""

    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    ERROR = "error"


class OrderManager:
    """Manages order lifecycle for arbitrage positions."""

    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}
        self.active_positions: list[Position] = []

    def create_position(
        self,
        symbol_a: str,
        exchange_a: str,
        symbol_b: str,
        exchange_b: str,
        scenario: str,
        leg_a_side: str,
        leg_a_quantity: float,
        leg_b_side: str,
        leg_b_quantity: float,
    ) -> Position:
        """Create a new arbitrage position."""
        position_id = f"{uuid.uuid4()}"
        position = Position(
            position_id=position_id,
            symbol_a=symbol_a,
            exchange_a=exchange_a,
            symbol_b=symbol_b,
            exchange_b=exchange_b,
            scenario=scenario,
            leg_a_side=leg_a_side,
            leg_a_quantity=leg_a_quantity,
            leg_b_side=leg_b_side,
            leg_b_quantity=leg_b_quantity,
        )
        self.positions[position_id] = position
        logger.info(
            "Created position %s: %s@%s vs %s@%s (scenario %s)",
            position_id,
            symbol_a,
            exchange_a,
            symbol_b,
            exchange_b,
            scenario,
        )
        return position

    def get_position(self, position_id: str) -> Position | None:
        """Get position by ID."""
        return self.positions.get(position_id)

    def get_active_positions(self) -> list[Position]:
        """Get all open positions."""
        return [p for p in self.positions.values() if p.is_open]

    async def entry_order(
        self,
        position: Position,
        client_a: ExchangeClient,
        client_b: ExchangeClient,
        history: "TradeHistory | None" = None,
    ) -> bool:
        """Execute entry orders for both legs of the position."""
        try:
            logger.info(
                "Placing entry orders for position %s", position.position_id
            )

            order_a = await client_a.place_market_order(
                symbol=position.symbol_a,
                side=position.leg_a_side,
                quantity=position.leg_a_quantity,
            )
            position.leg_a_order_id = order_a.order_id
            entry_price_a = order_a.price
            logger.debug(
                "Order A placed: %s %s %s @ %s",
                order_a.order_id,
                position.leg_a_side,
                position.leg_a_quantity,
                entry_price_a,
            )
            
            # Record order placement
            if history:
                history.record_order_placed(
                    position=position,
                    order_side=position.leg_a_side,
                    order_type="market",
                    quantity=position.leg_a_quantity,
                    price=entry_price_a,
                )

            order_b = await client_b.place_market_order(
                symbol=position.symbol_b,
                side=position.leg_b_side,
                quantity=position.leg_b_quantity,
            )
            position.leg_b_order_id = order_b.order_id
            entry_price_b = order_b.price
            logger.debug(
                "Order B placed: %s %s %s @ %s",
                order_b.order_id,
                position.leg_b_side,
                position.leg_b_quantity,
                entry_price_b,
            )
            
            # Record second order placement
            if history:
                history.record_order_placed(
                    position=position,
                    order_side=position.leg_b_side,
                    order_type="market",
                    quantity=position.leg_b_quantity,
                    price=entry_price_b,
                )

            position.mark_opened(entry_price_a, entry_price_b)
            self.active_positions.append(position)

            logger.info(
                "Position %s opened with spread %.4f%%",
                position.position_id,
                position.entry_spread * 100,
            )
            return True

        except Exception as e:
            logger.error("Failed to place entry orders: %s", e, exc_info=True)
            position.mark_error()
            return False

    async def exit_order(
        self,
        position: Position,
        client_a: ExchangeClient,
        client_b: ExchangeClient,
        history: "TradeHistory | None" = None,
    ) -> bool:
        """Execute exit orders for both legs of the position."""
        try:
            if not position.leg_a_order_id or not position.leg_b_order_id:
                logger.error(
                    "Cannot exit position %s: missing order IDs",
                    position.position_id,
                )
                return False

            logger.info("Closing position %s", position.position_id)
            position.status = PositionStatus.CLOSING

            exit_side_a = "sell" if position.leg_a_side == "buy" else "buy"
            exit_order_a = await client_a.place_market_order(
                symbol=position.symbol_a,
                side=exit_side_a,
                quantity=position.leg_a_quantity,
            )
            exit_price_a = exit_order_a.price
            logger.debug(
                "Exit order A: %s %s %s @ %s",
                exit_order_a.order_id,
                exit_side_a,
                position.leg_a_quantity,
                exit_price_a,
            )

            exit_side_b = "sell" if position.leg_b_side == "buy" else "buy"
            exit_order_b = await client_b.place_market_order(
                symbol=position.symbol_b,
                side=exit_side_b,
                quantity=position.leg_b_quantity,
            )
            exit_price_b = exit_order_b.price
            logger.debug(
                "Exit order B: %s %s %s @ %s",
                exit_order_b.order_id,
                exit_side_b,
                position.leg_b_quantity,
                exit_price_b,
            )

            position.mark_closed(exit_price_a, exit_price_b)
            if position in self.active_positions:
                self.active_positions.remove(position)

            logger.info(
                "Position %s closed with exit spread %.4f%% PnL: %.6f",
                position.position_id,
                position.exit_spread * 100 if position.exit_spread else 0,
                position.pnl or 0,
            )
            return True

        except Exception as e:
            logger.error("Failed to place exit orders: %s", e, exc_info=True)
            position.mark_error()
            return False
