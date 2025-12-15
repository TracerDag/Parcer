"""Order management for arbitrage strategies."""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import TYPE_CHECKING

from ..exchanges.protocol import ExchangeClient, Order

from .position import Position, PositionStatus
from .risk_manager import (
    ExecutionDiscrepancyError,
    InsufficientBalanceError,
    MaxPositionsError,
    RiskManager,
)

if TYPE_CHECKING:
    from ..history import TradeHistory
    from ..settings import Settings

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
        if self.history:
            self.history.record_position_created(position)
        return position

    def get_position(self, position_id: str) -> Position | None:
        """Get position by ID.

        If this manager is configured with history storage, it can lazily load
        positions created by previous processes.
        """
        cached = self.positions.get(position_id)
        if cached is not None:
            return cached

        if not self.history:
            return None

        loaded = self.history.load_position(position_id)
        if loaded is None:
            return None

        self.positions[position_id] = loaded
        return loaded

    def get_active_positions(self) -> list[Position]:
        """Get all open positions."""
        if self.history:
            return self.history.list_positions(status=PositionStatus.OPENED.value)
        return [p for p in self.positions.values() if p.is_open]

    def _open_positions_count(self) -> int:
        open_ids = {p.position_id for p in self.active_positions if p.is_open}
        if self.history:
            for position in self.history.list_positions(status=PositionStatus.OPENED.value):
                open_ids.add(position.position_id)
        return len(open_ids)

    @staticmethod
    def _opposite_side(side: str) -> str:
        return "sell" if side.lower() == "buy" else "buy"

    def _is_filled(self, order: Order) -> bool:
        if self.risk_manager:
            return self.risk_manager.is_order_filled(getattr(order, "status", None))
        return str(getattr(order, "status", "")).lower() in {"filled", "closed"}

    def _validate_order_execution(
        self,
        *,
        exchange_name: str,
        order: Order,
        expected_quantity: float,
    ) -> None:
        if self.risk_manager:
            self.risk_manager.validate_order_execution(
                exchange_name=exchange_name, order=order, expected_quantity=expected_quantity
            )
            return

        if not self._is_filled(order):
            raise ExecutionDiscrepancyError(
                f"Order not confirmed as filled on {exchange_name}: status={getattr(order, 'status', None)!r}"
            )

    async def entry_order(
        self,
        position: Position,
        client_a: ExchangeClient,
        client_b: ExchangeClient,
        history: "TradeHistory | None" = None,
        *,
        price_hint_a: float | None = None,
        price_hint_b: float | None = None,
    ) -> bool:
        """Execute entry orders for both legs of the position.

        Implements both-or-nothing execution: if one leg fails or is not
        confirmed as filled, the other leg is flattened via a compensating order.
        """
        hist = history or self.history

        logger.info("Placing entry orders for position %s", position.position_id)

        if self.risk_manager:
            try:
                self.risk_manager.check_position_limit(self._open_positions_count())

                await self.risk_manager.set_leverage_if_needed(
                    client_a, position.exchange_a, position.symbol_a
                )
                await self.risk_manager.set_leverage_if_needed(
                    client_b, position.exchange_b, position.symbol_b
                )

                await self.risk_manager.check_balance_sufficiency(
                    client=client_a,
                    exchange_name=position.exchange_a,
                    symbol=position.symbol_a,
                    side=position.leg_a_side,
                    quantity=position.leg_a_quantity,
                    price=price_hint_a,
                )
                await self.risk_manager.check_balance_sufficiency(
                    client=client_b,
                    exchange_name=position.exchange_b,
                    symbol=position.symbol_b,
                    side=position.leg_b_side,
                    quantity=position.leg_b_quantity,
                    price=price_hint_b,
                )
            except (InsufficientBalanceError, MaxPositionsError) as e:
                logger.error("Risk check failed: %s", e)
                if hist:
                    hist.record_position_error(position, str(e))
                position.mark_error()
                return False

        try:
            order_a = await client_a.place_market_order(
                symbol=position.symbol_a,
                side=position.leg_a_side,
                quantity=position.leg_a_quantity,
            )
        except Exception as e:
            logger.error(
                "Leg A order placement failed for position %s: %s",
                position.position_id,
                e,
                exc_info=True,
            )
            if hist:
                hist.record_order_failed(
                    position,
                    exchange=position.exchange_a,
                    symbol=position.symbol_a,
                    side=position.leg_a_side,
                    quantity=position.leg_a_quantity,
                    phase="entry",
                    error_message=str(e),
                )
                hist.record_position_error(position, f"Leg A failed: {e}")
            position.mark_error()
            return False

        position.leg_a_order_id = order_a.order_id
        if hist:
            hist.record_order_placed(
                position=position,
                order_side=position.leg_a_side,
                order_type="market",
                quantity=position.leg_a_quantity,
                price=order_a.price,
                order_id=order_a.order_id,
                exchange=position.exchange_a,
                symbol=position.symbol_a,
                status=order_a.status,
                phase="entry",
                metadata={"leg": "a"},
            )

        try:
            self._validate_order_execution(
                exchange_name=position.exchange_a,
                order=order_a,
                expected_quantity=position.leg_a_quantity,
            )
        except ExecutionDiscrepancyError as e:
            logger.error(
                "Leg A not confirmed for position %s (%s): %s",
                position.position_id,
                order_a.order_id,
                e,
            )
            await self._cleanup_unconfirmed_order(
                client=client_a,
                position=position,
                exchange=position.exchange_a,
                symbol=position.symbol_a,
                original_side=position.leg_a_side,
                quantity=position.leg_a_quantity,
                order_id=order_a.order_id,
                phase="entry",
                hist=hist,
            )
            if hist:
                hist.record_position_error(position, f"Leg A not confirmed: {e}")
            position.mark_error()
            return False

        try:
            order_b = await client_b.place_market_order(
                symbol=position.symbol_b,
                side=position.leg_b_side,
                quantity=position.leg_b_quantity,
            )
        except Exception as e:
            logger.error(
                "Leg B failed, rolling back leg A for position %s: %s",
                position.position_id,
                e,
                exc_info=True,
            )
            if hist:
                hist.record_order_failed(
                    position,
                    exchange=position.exchange_b,
                    symbol=position.symbol_b,
                    side=position.leg_b_side,
                    quantity=position.leg_b_quantity,
                    phase="entry",
                    error_message=str(e),
                )

            await self._hedge_market_order(
                client=client_a,
                position=position,
                exchange=position.exchange_a,
                symbol=position.symbol_a,
                side=self._opposite_side(position.leg_a_side),
                quantity=position.leg_a_quantity,
                original_order_id=order_a.order_id,
                reason="entry_leg_b_failed",
                hist=hist,
            )

            if hist:
                hist.record_position_error(
                    position, f"Leg B failed, rolled back leg A: {e}"
                )
            position.mark_error()
            return False

        position.leg_b_order_id = order_b.order_id
        if hist:
            hist.record_order_placed(
                position=position,
                order_side=position.leg_b_side,
                order_type="market",
                quantity=position.leg_b_quantity,
                price=order_b.price,
                order_id=order_b.order_id,
                exchange=position.exchange_b,
                symbol=position.symbol_b,
                status=order_b.status,
                phase="entry",
                metadata={"leg": "b"},
            )

        try:
            self._validate_order_execution(
                exchange_name=position.exchange_b,
                order=order_b,
                expected_quantity=position.leg_b_quantity,
            )
        except ExecutionDiscrepancyError as e:
            logger.error(
                "Leg B not confirmed for position %s (%s): %s",
                position.position_id,
                order_b.order_id,
                e,
            )

            await self._cleanup_unconfirmed_order(
                client=client_b,
                position=position,
                exchange=position.exchange_b,
                symbol=position.symbol_b,
                original_side=position.leg_b_side,
                quantity=position.leg_b_quantity,
                order_id=order_b.order_id,
                phase="entry",
                hist=hist,
            )
            await self._hedge_market_order(
                client=client_a,
                position=position,
                exchange=position.exchange_a,
                symbol=position.symbol_a,
                side=self._opposite_side(position.leg_a_side),
                quantity=position.leg_a_quantity,
                original_order_id=order_a.order_id,
                reason="entry_leg_b_unconfirmed",
                hist=hist,
            )

            if hist:
                hist.record_position_error(position, f"Leg B not confirmed: {e}")
            position.mark_error()
            return False

        position.mark_opened(order_a.price, order_b.price)
        if position not in self.active_positions:
            self.active_positions.append(position)

        if hist:
            hist.record_position_opened(position)

        logger.info(
            "Position %s opened with spread %.4f%%",
            position.position_id,
            position.entry_spread * 100,
        )
        return True

    async def _cleanup_unconfirmed_order(
        self,
        *,
        client: ExchangeClient,
        position: Position,
        exchange: str,
        symbol: str,
        original_side: str,
        quantity: float,
        order_id: str | None,
        phase: str,
        hist: "TradeHistory | None",
    ) -> None:
        cancel = getattr(client, "cancel_order", None)
        if callable(cancel) and order_id:
            try:
                await cancel(order_id, symbol)
                if hist:
                    hist.record_trade_event(
                        event_type="order_cancelled",
                        position=position,
                        order_type="cancel",
                        side=original_side,
                        quantity=quantity,
                        status="cancelled",
                        metadata={
                            "exchange": exchange,
                            "symbol": symbol,
                            "order_id": order_id,
                            "phase": phase,
                        },
                    )
            except Exception as e:
                logger.warning(
                    "Failed to cancel unconfirmed order %s on %s: %s",
                    order_id,
                    exchange,
                    e,
                )

        await self._hedge_market_order(
            client=client,
            position=position,
            exchange=exchange,
            symbol=symbol,
            side=self._opposite_side(original_side),
            quantity=quantity,
            original_order_id=order_id,
            reason=f"{phase}_unconfirmed_cleanup",
            hist=hist,
        )

    async def _hedge_market_order(
        self,
        *,
        client: ExchangeClient,
        position: Position,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        original_order_id: str | None,
        reason: str,
        hist: "TradeHistory | None",
    ) -> Order | None:
        try:
            hedge_order = await client.place_market_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
            )
            logger.info(
                "Hedge/rollback on %s for position %s: %s %s %s (orig=%s, hedge=%s)",
                exchange,
                position.position_id,
                side,
                quantity,
                symbol,
                original_order_id,
                hedge_order.order_id,
            )
            if hist:
                hist.record_order_rollback(
                    position,
                    original_order_id=original_order_id,
                    rollback_order_id=hedge_order.order_id,
                    exchange=exchange,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=hedge_order.price,
                    status=getattr(hedge_order, "status", None),
                    reason=reason,
                )
            return hedge_order
        except Exception as e:
            logger.error(
                "Failed to hedge/rollback on %s for position %s (orig=%s): %s",
                exchange,
                position.position_id,
                original_order_id,
                e,
                exc_info=True,
            )
            if hist:
                hist.record_order_failed(
                    position,
                    exchange=exchange,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    phase=reason,
                    error_message=str(e),
                )
            return None

    async def exit_order(
        self,
        position: Position,
        client_a: ExchangeClient,
        client_b: ExchangeClient,
        history: "TradeHistory | None" = None,
    ) -> bool:
        """Execute exit orders for both legs of the position."""
        hist = history or self.history

        if not position.leg_a_order_id or not position.leg_b_order_id:
            logger.error(
                "Cannot exit position %s: missing order IDs", position.position_id
            )
            return False

        logger.info("Closing position %s", position.position_id)
        position.status = PositionStatus.CLOSING

        exit_side_a = self._opposite_side(position.leg_a_side)
        exit_side_b = self._opposite_side(position.leg_b_side)

        try:
            exit_order_a = await client_a.place_market_order(
                symbol=position.symbol_a,
                side=exit_side_a,
                quantity=position.leg_a_quantity,
            )
        except Exception as e:
            logger.error(
                "Exit leg A failed for position %s: %s",
                position.position_id,
                e,
                exc_info=True,
            )
            if hist:
                hist.record_order_failed(
                    position,
                    exchange=position.exchange_a,
                    symbol=position.symbol_a,
                    side=exit_side_a,
                    quantity=position.leg_a_quantity,
                    phase="exit",
                    error_message=str(e),
                )
                hist.record_position_error(position, f"Exit leg A failed: {e}")
            position.mark_error()
            return False

        if hist:
            hist.record_order_placed(
                position=position,
                order_side=exit_side_a,
                order_type="market",
                quantity=position.leg_a_quantity,
                price=exit_order_a.price,
                order_id=exit_order_a.order_id,
                exchange=position.exchange_a,
                symbol=position.symbol_a,
                status=exit_order_a.status,
                phase="exit",
                metadata={"leg": "a"},
            )

        try:
            self._validate_order_execution(
                exchange_name=position.exchange_a,
                order=exit_order_a,
                expected_quantity=position.leg_a_quantity,
            )
        except ExecutionDiscrepancyError as e:
            logger.error(
                "Exit leg A not confirmed for position %s: %s",
                position.position_id,
                e,
            )
            await self._cleanup_unconfirmed_order(
                client=client_a,
                position=position,
                exchange=position.exchange_a,
                symbol=position.symbol_a,
                original_side=exit_side_a,
                quantity=position.leg_a_quantity,
                order_id=exit_order_a.order_id,
                phase="exit",
                hist=hist,
            )
            if hist:
                hist.record_position_error(position, f"Exit leg A not confirmed: {e}")
            position.mark_error()
            return False

        try:
            exit_order_b = await client_b.place_market_order(
                symbol=position.symbol_b,
                side=exit_side_b,
                quantity=position.leg_b_quantity,
            )
        except Exception as e:
            logger.error(
                "Exit leg B failed, attempting rollback of leg A for position %s: %s",
                position.position_id,
                e,
                exc_info=True,
            )

            if hist:
                hist.record_order_failed(
                    position,
                    exchange=position.exchange_b,
                    symbol=position.symbol_b,
                    side=exit_side_b,
                    quantity=position.leg_b_quantity,
                    phase="exit",
                    error_message=str(e),
                )

            # Re-open leg A to restore hedge
            await self._hedge_market_order(
                client=client_a,
                position=position,
                exchange=position.exchange_a,
                symbol=position.symbol_a,
                side=position.leg_a_side,
                quantity=position.leg_a_quantity,
                original_order_id=exit_order_a.order_id,
                reason="exit_leg_b_failed_reopen_leg_a",
                hist=hist,
            )

            if hist:
                hist.record_position_error(position, f"Exit leg B failed: {e}")
            position.mark_error()
            return False

        if hist:
            hist.record_order_placed(
                position=position,
                order_side=exit_side_b,
                order_type="market",
                quantity=position.leg_b_quantity,
                price=exit_order_b.price,
                order_id=exit_order_b.order_id,
                exchange=position.exchange_b,
                symbol=position.symbol_b,
                status=exit_order_b.status,
                phase="exit",
                metadata={"leg": "b"},
            )

        try:
            self._validate_order_execution(
                exchange_name=position.exchange_b,
                order=exit_order_b,
                expected_quantity=position.leg_b_quantity,
            )
        except ExecutionDiscrepancyError as e:
            logger.error(
                "Exit leg B not confirmed for position %s: %s",
                position.position_id,
                e,
            )
            await self._cleanup_unconfirmed_order(
                client=client_b,
                position=position,
                exchange=position.exchange_b,
                symbol=position.symbol_b,
                original_side=exit_side_b,
                quantity=position.leg_b_quantity,
                order_id=exit_order_b.order_id,
                phase="exit",
                hist=hist,
            )
            await self._hedge_market_order(
                client=client_a,
                position=position,
                exchange=position.exchange_a,
                symbol=position.symbol_a,
                side=position.leg_a_side,
                quantity=position.leg_a_quantity,
                original_order_id=exit_order_a.order_id,
                reason="exit_leg_b_unconfirmed_reopen_leg_a",
                hist=hist,
            )

            if hist:
                hist.record_position_error(position, f"Exit leg B not confirmed: {e}")
            position.mark_error()
            return False

        position.mark_closed(exit_order_a.price, exit_order_b.price)

        if position in self.active_positions:
            self.active_positions.remove(position)

        if hist:
            hist.record_position_closed(position)

        logger.info(
            "Position %s closed with exit spread %.4f%% PnL: %.6f",
            position.position_id,
            (position.exit_spread or 0.0) * 100,
            position.pnl or 0.0,
        )
        return True
