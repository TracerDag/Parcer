"""Gate.io exchange adapter."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None

from .base import BaseExchangeClient, ProxyConfig
from .protocol import Balance, Order


class GateClient(BaseExchangeClient):
    """Gate.io exchange client."""

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
            "gate",
            api_key,
            api_secret,
            sandbox=sandbox,
            proxy=proxy,
            **options,
        )
        self.session = None

    def get_base_url(self) -> str:
        if self.sandbox:
            return "https://api.gateio.ws"
        return "https://api.gateio.ws"

    def get_ws_url(self) -> str:
        if self.sandbox:
            return "wss://api.gateio.ws/ws/v4/"
        return "wss://api.gateio.ws/ws/v4/"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            if aiohttp is None:
                raise ImportError("aiohttp is required for Gate adapter")
            connector = aiohttp.TCPConnector()
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    def _get_headers(self, signature: str, timestamp: str) -> dict[str, str]:
        return {
            "KEY": self.api_key,
            "Timestamp": timestamp,
            "SIGN": signature,
            "Content-Type": "application/json",
            "User-Agent": "parcer/1.0",
        }

    def _sign_request(self, method: str, path: str, body: str = "") -> tuple[str, str]:
        """Generate Gate.io signature."""
        timestamp = str(int(time.time()))
        message = "\n".join([method, path, body, timestamp])
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha512,
        ).hexdigest()
        return signature, timestamp

    async def get_balance(self, asset: str | None = None) -> list[Balance] | Balance:
        """Fetch account balance."""
        session = await self._ensure_session()
        path = "/api/v4/spot/accounts"
        signature, timestamp = self._sign_request("GET", path)
        url = f"{self.get_base_url()}{path}"

        async with session.get(url, headers=self._get_headers(signature, timestamp)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch balance: {resp.status}")
            data = await resp.json()

        balances = []
        for account in data:
            for balance_item in account.get("balances", []):
                curr = balance_item.get("currency")
                free = float(balance_item.get("available", 0))
                locked = float(balance_item.get("locked", 0))
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
        path = "/api/v4/spot/orders"

        body = json.dumps({
            "currency_pair": symbol.upper(),
            "side": side.lower(),
            "amount": str(quantity),
            "type": "market",
        })

        signature, timestamp = self._sign_request("POST", path, body)
        url = f"{self.get_base_url()}{path}"

        async with session.post(url, data=body, headers=self._get_headers(signature, timestamp)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to place order: {resp.status}")
            data = await resp.json()

        return Order(
            str(data.get("id")),
            symbol.upper(),
            side.lower(),
            quantity,
            0.0,
            data.get("status", "").lower(),
        )

    async def cancel_order(self, order_id: str, symbol: str | None = None) -> Order:
        """Cancel an active order."""
        if not symbol:
            raise ValueError("Gate requires symbol to cancel order")

        session = await self._ensure_session()
        path = f"/api/v4/spot/orders/{order_id}"

        signature, timestamp = self._sign_request("DELETE", path)
        url = f"{self.get_base_url()}{path}"

        async with session.delete(url, headers=self._get_headers(signature, timestamp)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to cancel order: {resp.status}")
            data = await resp.json()

        return Order(
            order_id,
            symbol.upper(),
            "",
            0,
            0.0,
            data.get("status", "").lower(),
        )

    async def set_leverage(self, leverage: float, symbol: str | None = None) -> None:
        """Set leverage for perpetual trading."""
        if not symbol:
            raise ValueError("Gate requires symbol to set leverage")

        session = await self._ensure_session()
        path = "/api/v4/futures/usdt/positions"

        body = json.dumps({
            "contract": symbol.lower() + "_usdt",
            "leverage": str(int(leverage)),
        })

        signature, timestamp = self._sign_request("POST", path, body)
        url = f"{self.get_base_url()}{path}"

        async with session.post(url, data=body, headers=self._get_headers(signature, timestamp)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to set leverage: {resp.status}")

    async def _fetch_mark_price(self, symbol: str) -> float | None:
        """Fetch current mark price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/api/v4/futures/usdt/tickers"
        params = {"contract": symbol.lower() + "_usdt"}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data:
                    return float(data[0].get("mark_price"))
                return None
        except Exception:
            return None

    async def _fetch_spot_price(self, symbol: str) -> float | None:
        """Fetch current spot price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/api/v4/spot/tickers"
        params = {"currency_pair": symbol.upper()}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data:
                    return float(data[0].get("last"))
                return None
        except Exception:
            return None

    async def close(self) -> None:
        """Close connections."""
        if self.session:
            await self.session.close()
