"""Protocol definition for exchange clients."""

from __future__ import annotations

from typing import AsyncIterator, Protocol, Any


class Balance:
    """Represents account balance for a single asset."""

    def __init__(self, asset: str, free: float, used: float):
        self.asset = asset
        self.free = free
        self.used = used

    @property
    def total(self) -> float:
        return self.free + self.used


class Order:
    """Represents a market order."""

    def __init__(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        status: str,
    ):
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.status = status


class PriceUpdate:
    """Represents a price update (mark price or spot price)."""

    def __init__(self, symbol: str, price: float, timestamp: int | None = None):
        self.symbol = symbol
        self.price = price
        self.timestamp = timestamp


class ExchangeClient(Protocol):
    """Protocol for exchange connectivity."""

    def __init__(self, name: str, api_key: str, api_secret: str, **kwargs: Any):
        """Initialize exchange client.

        Args:
            name: Exchange name (e.g., 'binance', 'okx')
            api_key: API key for authentication
            api_secret: API secret for authentication
            **kwargs: Additional options (passphrase, sandbox, proxy, etc.)
        """
        ...

    async def get_balance(self, asset: str | None = None) -> list[Balance] | Balance:
        """Fetch account balance.

        Args:
            asset: Specific asset to fetch balance for (optional)

        Returns:
            Single Balance if asset specified, list of Balance objects otherwise
        """
        ...

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Order:
        """Place a market order.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            side: 'buy' or 'sell'
            quantity: Order quantity

        Returns:
            Order object with order_id and status
        """
        ...

    async def cancel_order(self, order_id: str, symbol: str | None = None) -> Order:
        """Cancel an active order.

        Args:
            order_id: Order ID to cancel
            symbol: Trading symbol (optional, required by some exchanges)

        Returns:
            Cancelled Order object
        """
        ...

    async def set_leverage(self, leverage: float, symbol: str | None = None) -> None:
        """Set leverage for perpetual trading.

        Args:
            leverage: Leverage multiplier (e.g., 2.0, 5.0)
            symbol: Trading symbol (optional, required by some exchanges)
        """
        ...

    async def stream_mark_price(self, symbol: str) -> AsyncIterator[PriceUpdate]:
        """Stream mark prices for a symbol.

        Uses WebSocket if available, falls back to REST polling.

        Args:
            symbol: Trading symbol

        Yields:
            PriceUpdate objects with symbol and price
        """
        ...

    async def stream_spot_price(self, symbol: str) -> AsyncIterator[PriceUpdate]:
        """Stream spot prices for a symbol.

        Uses WebSocket if available, falls back to REST polling.

        Args:
            symbol: Trading symbol

        Yields:
            PriceUpdate objects with symbol and price
        """
        ...

    async def close(self) -> None:
        """Close connections (WebSocket, HTTP session, etc.)."""
        ...
