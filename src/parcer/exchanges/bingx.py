"""BingX exchange adapter."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None

from .base import BaseExchangeClient, ProxyConfig
from .protocol import Balance, Order


class BingXClient(BaseExchangeClient):
    """BingX exchange client."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        sandbox: bool = False,
        proxy: ProxyConfig | None = None,
        **options: Any,
    ):
        super().__init__(
            "bingx",
            api_key,
            api_secret,
            sandbox=sandbox,
            proxy=proxy,
            **options,
        )
        self.session = None

    def get_base_url(self) -> str:
        if self.sandbox:
            return "https://open-api-testnet.bingx.com"
        return "https://open-api.bingx.com"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            if aiohttp is None:
                raise ImportError("aiohttp is required for BingX adapter")
            connector = aiohttp.TCPConnector()
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    def _get_headers(self, signature: str, timestamp: str) -> dict[str, str]:
        return {
            "X-BX-APIKEY": self.api_key,
            "X-BX-TIMESTAMP": timestamp,
            "X-BX-SIGN": signature,
            "Content-Type": "application/json",
            "User-Agent": "parcer/1.0",
        }

    def _sign_request(self, query_string: str) -> tuple[str, str]:
        """Generate BingX signature."""
        timestamp = str(int(time.time() * 1000))
        message = query_string + "&timestamp=" + timestamp
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return signature, timestamp

    async def get_balance(self, asset: str | None = None) -> list[Balance] | Balance:
        """Fetch account balance."""
        session = await self._ensure_session()
        path = "/openApi/spot/v1/account/balance"

        query_string = ""
        signature, timestamp = self._sign_request(query_string)
        url = f"{self.get_base_url()}{path}"

        async with session.get(url, headers=self._get_headers(signature, timestamp)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch balance: {resp.status}")
            data = await resp.json()

        balances = []
        for item in data.get("data", {}).get("balances", []):
            curr = item.get("asset")
            free = float(item.get("free", 0))
            locked = float(item.get("locked", 0))
            if free > 0 or locked > 0:
                balances.append(Balance(curr, free, locked))

        if asset:
            for b in balances:
                if b.asset.upper() == asset.upper():
                    return b
            return Balance(asset.upper(), 0, 0)

        return balances

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Order:
        """Place a market order."""
        session = await self._ensure_session()
        path = "/openApi/spot/v1/trade/order"

        query_dict = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": str(quantity),
        }
        query_string = urlencode(query_dict)
        signature, timestamp = self._sign_request(query_string)

        url = f"{self.get_base_url()}{path}?{query_string}"

        async with session.post(url, headers=self._get_headers(signature, timestamp)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to place order: {resp.status}")
            data = await resp.json()

        order_data = data.get("data", {})
        return Order(
            order_data.get("orderId"),
            symbol.upper(),
            side.lower(),
            quantity,
            0.0,
            order_data.get("status", "").lower(),
        )

    async def cancel_order(self, order_id: str, symbol: str | None = None) -> Order:
        """Cancel an active order."""
        if not symbol:
            raise ValueError("BingX requires symbol to cancel order")

        session = await self._ensure_session()
        path = "/openApi/spot/v1/trade/cancel"

        query_dict = {
            "symbol": symbol.upper(),
            "orderId": order_id,
        }
        query_string = urlencode(query_dict)
        signature, timestamp = self._sign_request(query_string)

        url = f"{self.get_base_url()}{path}?{query_string}"

        async with session.post(url, headers=self._get_headers(signature, timestamp)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to cancel order: {resp.status}")
            data = await resp.json()

        order_data = data.get("data", {})
        return Order(
            order_id,
            symbol.upper(),
            "",
            0,
            0.0,
            order_data.get("status", "").lower(),
        )

    async def _fetch_spot_price(self, symbol: str) -> float | None:
        """Fetch current spot price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/openApi/spot/v1/market/ticker"
        params = {"symbol": symbol.upper()}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return float(data.get("data", {}).get("lastPrice"))
        except Exception:
            return None

    async def close(self) -> None:
        """Close connections."""
        if self.session:
            await self.session.close()
