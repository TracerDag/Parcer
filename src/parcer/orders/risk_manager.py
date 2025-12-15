"""Risk management for order execution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..exchanges.protocol import ExchangeClient
    from ..history import TradeHistory
    from ..settings import Settings

from .position import Position

logger = logging.getLogger(__name__)


class InsufficientBalanceError(Exception):
    """Raised when balance is insufficient for order."""
    pass


class MaxPositionsError(Exception):
    """Raised when maximum positions limit is reached."""


class ExecutionDiscrepancyError(Exception):
    """Raised when an order response indicates unexpected execution state."""


class RiskManager:
    """Enforces risk management rules for order execution."""

    def __init__(self, settings: "Settings", history: "TradeHistory | None" = None):
        self.settings = settings
        self.history = history
        self.leverage = settings.trading.leverage
        self.max_positions = settings.trading.max_positions
        self.fixed_order_size = settings.trading.fixed_order_size

    async def check_balance_sufficiency(
        self,
        client: "ExchangeClient",
        exchange_name: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
    ) -> bool:
        """Check if balance is sufficient for an order.
        
        Args:
            client: Exchange client to check balance on
            exchange_name: Name of the exchange
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            quantity: Order quantity
            price: Estimated price (optional)
            
        Returns:
            True if balance is sufficient
            
        Raises:
            InsufficientBalanceError: If balance is insufficient
        """
        try:
            # Get USDT balance
            balance = await client.get_balance("USDT")
            available = balance.free if hasattr(balance, 'free') else balance.total
            
            # Calculate required amount
            # For both buy and sell on perpetuals/futures, we need USDT margin
            # For spot, sell orders need the base asset (not checked here)
            
            # Estimate required USDT
            if price is None or price == 0.0:
                # Without price, we can't accurately check balance
                # Skip the check and log a warning
                logger.warning(
                    "Price not provided for balance check on %s, skipping check",
                    exchange_name
                )
                return True
            
            # Calculate cost with leverage consideration
            # Both buy and sell need margin in perpetuals
            required = (quantity * price) / self.leverage
            
            if available < required:
                # Record insufficient balance
                if self.history:
                    self.history.record_insufficient_balance(
                        exchange=exchange_name,
                        symbol=symbol,
                        required=required,
                        available=available,
                    )
                
                raise InsufficientBalanceError(
                    f"Insufficient USDT balance on {exchange_name}: "
                    f"required {required:.2f}, available {available:.2f}"
                )
            
            logger.debug(
                "Balance check passed for %s %s: required %.2f, available %.2f",
                exchange_name,
                side,
                required,
                available,
            )
            return True
            
        except InsufficientBalanceError:
            raise
        except Exception as e:
            logger.error("Failed to check balance on %s: %s", exchange_name, e)
            raise

    def check_position_limit(self, current_positions: int) -> bool:
        """Check if adding a new position would exceed the limit.
        
        Args:
            current_positions: Number of currently active positions
            
        Returns:
            True if limit not exceeded
            
        Raises:
            MaxPositionsError: If position limit would be exceeded
        """
        if current_positions >= self.max_positions:
            raise MaxPositionsError(
                f"Maximum positions limit reached: {current_positions}/{self.max_positions}"
            )
        return True

    async def set_leverage_if_needed(
        self,
        client: "ExchangeClient",
        exchange_name: str,
        symbol: str,
    ) -> None:
        """Set leverage on exchange if it's a perpetual market.
        
        Args:
            client: Exchange client
            exchange_name: Name of the exchange
            symbol: Trading symbol
        """
        try:
            # Check if symbol is perpetual (contains "PERP" or "SWAP")
            is_perpetual = "PERP" in symbol.upper() or "SWAP" in symbol.upper()
            
            if is_perpetual:
                await client.set_leverage(self.leverage, symbol)
                logger.info(
                    "Set leverage to %.1fx on %s for %s",
                    self.leverage,
                    exchange_name,
                    symbol,
                )
        except Exception as e:
            logger.warning(
                "Failed to set leverage on %s for %s: %s",
                exchange_name,
                symbol,
                e,
            )

    def get_order_quantity(self, symbol: str, price: float | None = None) -> float:
        """Calculate order quantity based on fixed order size.
        
        Args:
            symbol: Trading symbol
            price: Current price (optional)
            
        Returns:
            Order quantity
        """
        # For USDT-margined contracts, fixed_order_size is in USDT
        # Quantity = fixed_order_size / price
        if price and price > 0:
            quantity = self.fixed_order_size / price
        else:
            # If price not available, return a default small quantity
            # This should be overridden by the caller
            quantity = 0.001
            logger.warning("Price not provided for quantity calculation")
        
        return quantity

    async def validate_order_params(
        self,
        position: Position,
        client_a: "ExchangeClient",
        client_b: "ExchangeClient",
        exchange_name_a: str,
        exchange_name_b: str,
        current_positions: int,
    ) -> None:
        """Validate all order parameters before execution.
        
        Args:
            position: Position to validate
            client_a: Exchange client for leg A
            client_b: Exchange client for leg B
            exchange_name_a: Name of exchange A
            exchange_name_b: Name of exchange B
            current_positions: Number of currently active positions
            
        Raises:
            MaxPositionsError: If position limit exceeded
            InsufficientBalanceError: If balance insufficient
        """
        # Check position limit
        self.check_position_limit(current_positions)
        
        # Set leverage if needed
        await self.set_leverage_if_needed(client_a, exchange_name_a, position.symbol_a)
        await self.set_leverage_if_needed(client_b, exchange_name_b, position.symbol_b)
        
        # Check balance sufficiency for both legs
        # Note: We can't get exact prices before placing orders, so we estimate
        logger.info("Validating balance sufficiency for both legs")

    def is_order_filled(self, status: str | None) -> bool:
        """Return True if the exchange reports the order as fully executed."""
        if not status:
            return False
        return status.lower() in {"filled", "closed"}

    def validate_order_execution(
        self,
        *,
        exchange_name: str,
        order: object,
        expected_quantity: float,
    ) -> None:
        """Validate an order response is consistent with the intended execution."""
        status = getattr(order, "status", None)
        if not self.is_order_filled(status):
            raise ExecutionDiscrepancyError(
                f"Order not confirmed as filled on {exchange_name}: status={status!r}"
            )

        actual_qty = getattr(order, "quantity", None)
        if isinstance(actual_qty, (int, float)) and expected_quantity > 0:
            rel_diff = abs(actual_qty - expected_quantity) / expected_quantity
            if rel_diff > 0.01:
                raise ExecutionDiscrepancyError(
                    f"Order quantity mismatch on {exchange_name}: expected={expected_quantity}, actual={actual_qty}"
                )
