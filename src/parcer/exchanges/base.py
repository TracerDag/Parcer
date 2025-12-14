"""Base client class for exchange adapters."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from .normalization import normalize_symbol
from .protocol import Balance, Order, PriceUpdate

logger = logging.getLogger(__name__)


class ProxyConfig:
    """HTTP proxy configuration."""

    def __init__(self, url: str | None = None, username: str | None = None, password: str | None = None):
        self.url = url
        self.username = username
        self.password = password

    @property
    def proxy_url(self) -> str | None:
        if not self.url:
            return None
        if self.username and self.password:
            protocol = self.url.split("://")[0] if "://" in self.url else "http"
            rest = self.url.split("://")[1] if "://" in self.url else self.url
            return f"{protocol}://{self.username}:{self.password}@{rest}"
        return self.url


class BaseExchangeClient(ABC):
    """Base class for all exchange adapters."""

    def __init__(
        self,
        name: str,
        api_key: str,
        api_secret: str,
        *,
        passphrase: str | None = None,
        sandbox: bool = False,
        proxy: ProxyConfig | None = None,
        **options: Any,
    ):
        """Initialize exchange client.

        Args:
            name: Exchange name
            api_key: API key
            api_secret: API secret
            passphrase: API passphrase (OKX, Bybit, Bitget)
            sandbox: Use sandbox/testnet environment
            proxy: Proxy configuration
            **options: Additional exchange-specific options
        """
        self.name = name
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.sandbox = sandbox
        self.proxy = proxy or ProxyConfig()
        self.options = options

    @staticmethod
    def generate_signature(secret: str, message: str, method: str = "hmac-sha256") -> str:
        """Generate HMAC-SHA256 signature.

        Args:
            secret: Secret key
            message: Message to sign
            method: Signature method (default: hmac-sha256)

        Returns:
            Hex-encoded signature
        """
        if method == "hmac-sha256":
            return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        else:
            raise ValueError(f"Unsupported signature method: {method}")

    def get_base_url(self) -> str:
        """Get base API URL.

        Can be overridden by subclasses to handle sandbox/testnet URLs.

        Returns:
            Base API URL
        """
        return "https://api.example.com"

    def get_ws_url(self) -> str | None:
        """Get WebSocket URL.

        Returns:
            WebSocket URL or None if not available
        """
        return None

    @abstractmethod
    async def get_balance(self, asset: str | None = None) -> list[Balance] | Balance:
        """Fetch account balance."""
        ...

    @abstractmethod
    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Order:
        """Place a market order."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str | None = None) -> Order:
        """Cancel an active order."""
        ...

    async def set_leverage(self, leverage: float, symbol: str | None = None) -> None:
        """Set leverage for perpetual trading.

        Default implementation raises NotImplementedError.
        Override in subclasses that support leverage.
        """
        raise NotImplementedError(f"{self.name} does not support leverage adjustment")

    async def stream_mark_price(self, symbol: str) -> AsyncIterator[PriceUpdate]:
        """Stream mark prices for a symbol.

        Default implementation uses REST polling.
        Override in subclasses that support WebSocket.
        """
        async for price_update in self._rest_poll_mark_price(symbol):
            yield price_update

    async def stream_spot_price(self, symbol: str) -> AsyncIterator[PriceUpdate]:
        """Stream spot prices for a symbol.

        Default implementation uses REST polling.
        Override in subclasses that support WebSocket.
        """
        async for price_update in self._rest_poll_spot_price(symbol):
            yield price_update

    async def _rest_poll_mark_price(self, symbol: str, interval: float = 1.0) -> AsyncIterator[PriceUpdate]:
        """REST polling for mark prices."""
        while True:
            try:
                price = await self._fetch_mark_price(symbol)
                if price is not None:
                    yield PriceUpdate(symbol, price, int(time.time() * 1000))
            except Exception as e:
                logger.error(f"Error fetching mark price for {symbol}: {e}")
            await asyncio.sleep(interval)

    async def _rest_poll_spot_price(self, symbol: str, interval: float = 1.0) -> AsyncIterator[PriceUpdate]:
        """REST polling for spot prices."""
        while True:
            try:
                price = await self._fetch_spot_price(symbol)
                if price is not None:
                    yield PriceUpdate(symbol, price, int(time.time() * 1000))
            except Exception as e:
                logger.error(f"Error fetching spot price for {symbol}: {e}")
            await asyncio.sleep(interval)

    async def _fetch_mark_price(self, symbol: str) -> float | None:
        """Fetch current mark price."""
        raise NotImplementedError()

    async def _fetch_spot_price(self, symbol: str) -> float | None:
        """Fetch current spot price."""
        raise NotImplementedError()

    async def close(self) -> None:
        """Close connections."""
        pass
