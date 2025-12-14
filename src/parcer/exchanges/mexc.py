"""MEXC exchange adapter (REST only)."""

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


class MEXCClient(BaseExchangeClient):
    """MEXC exchange client (REST only)."""

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
            "mexc",
            api_key,
            api_secret,
            sandbox=sandbox,
            proxy=proxy,
            **options,
        )
        self.session = None

    def get_base_url(self) -> str:
        if self.sandbox:
            return "https://api-sandbox.mexc.com"
        return "https://api.mexc.com"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            if aiohttp is None:
                raise ImportError("aiohttp is required for MEXC adapter")
            connector = aiohttp.TCPConnector()
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    def _get_headers(self) -> dict[str, str]:
        return {
            "X-MEXC-APIKEY": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "parcer/1.0",
        }

    def _sign_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add signature to params."""
        params = dict(params)
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode(),
            query_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    async def get_balance(self, asset: str | None = None) -> list[Balance] | Balance:
        """Fetch account balance."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/api/v3/account"
        params = self._sign_params({"timestamp": int(time.time() * 1000)})

        async with session.get(url, params=params, headers=self._get_headers()) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch balance: {resp.status}")
            data = await resp.json()

        balances = [
            Balance(b["asset"], float(b["free"]), float(b["locked"]))
            for b in data.get("balances", [])
            if float(b["free"]) > 0 or float(b["locked"]) > 0
        ]

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
        url = f"{self.get_base_url()}/api/v3/order"
        params = self._sign_params({
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity,
            "timestamp": int(time.time() * 1000),
        })

        async with session.post(url, params=params, headers=self._get_headers()) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to place order: {resp.status}")
            data = await resp.json()

        return Order(
            str(data["orderId"]),
            data["symbol"],
            data["side"].lower(),
            float(data["executedQty"]),
            0.0,
            data["status"].lower(),
        )

    async def cancel_order(self, order_id: str, symbol: str | None = None) -> Order:
        """Cancel an active order."""
        if not symbol:
            raise ValueError("MEXC requires symbol to cancel order")

        session = await self._ensure_session()
        url = f"{self.get_base_url()}/api/v3/order"
        params = self._sign_params({
            "symbol": symbol.upper(),
            "orderId": order_id,
            "timestamp": int(time.time() * 1000),
        })

        async with session.delete(url, params=params, headers=self._get_headers()) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to cancel order: {resp.status}")
            data = await resp.json()

        return Order(
            str(data["orderId"]),
            data["symbol"],
            data["side"].lower(),
            float(data["executedQty"]),
            0.0,
            data["status"].lower(),
        )

    async def _fetch_spot_price(self, symbol: str) -> float | None:
        """Fetch current spot price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/api/v3/ticker/price"
        params = {"symbol": symbol.upper()}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return float(data.get("price"))
        except Exception:
            return None

    async def close(self) -> None:
        """Close connections."""
        if self.session:
            await self.session.close()
