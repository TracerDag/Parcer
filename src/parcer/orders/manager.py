"""Order management for arbitrage strategies."""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..history import TradeHistory
    from ..settings import Settings

from ..exchanges.protocol import ExchangeClient, Order

from .position import Position, PositionStatus
from .risk_manager import RiskManager, InsufficientBalanceError, MaxPositionsError

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
    """Manages order lifecycle for arbitrage positions with risk management."""

    def __init__(
        self,
        settings: "Settings | None" = None,
        history: "TradeHistory | None" = None,
    ) -> None:
        self.positions: dict[str, Position] = {}
        self.active_positions: list[Position] = []
        self.settings = settings
        self.history = history
        
        # Initialize risk manager if settings provided
        if settings:
            self.risk_manager = RiskManager(settings, history)
        else:
            self.risk_manager = None

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
        """Execute entry orders for both legs of the position with risk management.
        
        Implements "both-or-nothing" execution: if one leg fails, the other is rolled back.
        """
        # Use provided history or instance history
        hist = history or self.history
        
        try:
            logger.info(
                "Placing entry orders for position %s", position.position_id
            )
            
            # Risk management checks
            if self.risk_manager:
                try:
                    # Check position limit
                    self.risk_manager.check_position_limit(len(self.active_positions))
                    
                    # Set leverage if needed
                    await self.risk_manager.set_leverage_if_needed(
                        client_a, position.exchange_a, position.symbol_a
                    )
                    await self.risk_manager.set_leverage_if_needed(
                        client_b, position.exchange_b, position.symbol_b
                    )
                    
                    # Check balance sufficiency for leg A
                    await self.risk_manager.check_balance_sufficiency(
                        client_a,
                        position.exchange_a,
                        position.symbol_a,
                        position.leg_a_side,
                        position.leg_a_quantity,
                    )
                    
                    # Check balance sufficiency for leg B
                    await self.risk_manager.check_balance_sufficiency(
                        client_b,
                        position.exchange_b,
                        position.symbol_b,
                        position.leg_b_side,
                        position.leg_b_quantity,
                    )
                    
                except (InsufficientBalanceError, MaxPositionsError) as e:
                    logger.error("Risk check failed: %s", e)
                    if hist:
                        hist.record_position_error(position, str(e))
                    position.mark_error()
                    return False

            # Place first leg (leg A)
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
            if hist:
                hist.record_order_placed(
                    position=position,
                    order_side=position.leg_a_side,
                    order_type="market",
                    quantity=position.leg_a_quantity,
                    price=entry_price_a,
                )

            # Try to place second leg (leg B)
            # If this fails, rollback leg A
            try:
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
                if hist:
                    hist.record_order_placed(
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
                # Leg B failed - rollback leg A
                logger.error(
                    "Leg B failed, rolling back leg A (order %s): %s",
                    order_a.order_id,
                    e,
                    exc_info=True,
                )
                
                # Execute rollback by placing opposite order
                await self._rollback_order(
                    client_a,
                    position.symbol_a,
                    position.leg_a_side,
                    position.leg_a_quantity,
                    order_a.order_id,
                )
                
                if hist:
                    hist.record_position_error(
                        position,
                        f"Leg B failed, rolled back leg A: {e}",
                    )
                
                position.mark_error()
                return False

        except Exception as e:
            logger.error("Failed to place entry orders: %s", e, exc_info=True)
            if hist:
                hist.record_position_error(position, str(e))
            position.mark_error()
            return False
    
    async def _rollback_order(
        self,
        client: ExchangeClient,
        symbol: str,
        original_side: str,
        quantity: float,
        original_order_id: str,
    ) -> None:
        """Rollback an order by placing an opposite market order.
        
        Args:
            client: Exchange client
            symbol: Trading symbol
            original_side: Side of the original order
            quantity: Quantity to rollback
            original_order_id: ID of the original order
        """
        try:
            # Place opposite order to close the position
            rollback_side = "sell" if original_side == "buy" else "buy"
            logger.info(
                "Rolling back order %s: placing %s %s %s",
                original_order_id,
                rollback_side,
                quantity,
                symbol,
            )
            
            rollback_order = await client.place_market_order(
                symbol=symbol,
                side=rollback_side,
                quantity=quantity,
            )
            
            logger.info(
                "Rollback successful: order %s closed with %s",
                original_order_id,
                rollback_order.order_id,
            )
            
        except Exception as e:
            logger.error(
                "Failed to rollback order %s: %s. Manual intervention required!",
                original_order_id,
                e,
                exc_info=True,
            )

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
