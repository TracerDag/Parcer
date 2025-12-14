"""KuCoin exchange adapter."""

from __future__ import annotations

import base64
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


class KuCoinClient(BaseExchangeClient):
    """KuCoin exchange client."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        passphrase: str,
        sandbox: bool = False,
        proxy: ProxyConfig | None = None,
        **options: Any,
    ):
        super().__init__(
            "kucoin",
            api_key,
            api_secret,
            passphrase=passphrase,
            sandbox=sandbox,
            proxy=proxy,
            **options,
        )
        self.session = None

    def get_base_url(self) -> str:
        if self.sandbox:
            return "https://openapi-sandbox.kucoin.com"
        return "https://api.kucoin.com"

    def get_ws_url(self) -> str:
        if self.sandbox:
            return "wss://ws-sandbox.kucoin.com/socket.io"
        return "wss://ws.kucoin.com/socket.io"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            if aiohttp is None:
                raise ImportError("aiohttp is required for KuCoin adapter")
            connector = aiohttp.TCPConnector()
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    def _get_headers(self, signature: str, timestamp: str, nonce: str) -> dict[str, str]:
        return {
            "KC-API-KEY": self.api_key,
            "KC-API-SIGN": signature,
            "KC-API-TIMESTAMP": timestamp,
            "KC-API-KEY-VERSION": "1",
            "KC-API-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "User-Agent": "parcer/1.0",
        }

    def _sign_request(self, method: str, path: str, body: str = "") -> tuple[str, str, str]:
        """Generate KuCoin signature."""
        nonce = str(int(time.time() * 1000))
        message = nonce + method + path + body
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode(),
                message.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        return signature, nonce, nonce

    async def get_balance(self, asset: str | None = None) -> list[Balance] | Balance:
        """Fetch account balance."""
        session = await self._ensure_session()
        path = "/api/v1/accounts"
        signature, timestamp, nonce = self._sign_request("GET", path)
        url = f"{self.get_base_url()}{path}"

        async with session.get(url, headers=self._get_headers(signature, timestamp, nonce)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch balance: {resp.status}")
            data = await resp.json()

        balances = []
        for item in data.get("data", []):
            if item.get("type") == "trade":
                curr = item.get("currency")
                free = float(item.get("available", 0))
                locked = float(item.get("holds", 0))
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
        path = "/api/v1/orders"

        body = json.dumps({
            "symbol": symbol.upper(),
            "side": side.lower(),
            "size": str(quantity),
            "type": "market",
        })

        signature, timestamp, nonce = self._sign_request("POST", path, body)
        url = f"{self.get_base_url()}{path}"

        async with session.post(url, data=body, headers=self._get_headers(signature, timestamp, nonce)) as resp:
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
            "new",
        )

    async def cancel_order(self, order_id: str, symbol: str | None = None) -> Order:
        """Cancel an active order."""
        session = await self._ensure_session()
        path = f"/api/v1/orders/{order_id}"

        signature, timestamp, nonce = self._sign_request("DELETE", path)
        url = f"{self.get_base_url()}{path}"

        async with session.delete(url, headers=self._get_headers(signature, timestamp, nonce)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to cancel order: {resp.status}")
            data = await resp.json()

        order_data = data.get("data", {})
        return Order(
            order_id,
            symbol or "",
            "",
            0,
            0.0,
            "cancelled",
        )

    async def set_leverage(self, leverage: float, symbol: str | None = None) -> None:
        """Set leverage for perpetual trading."""
        if not symbol:
            raise ValueError("KuCoin requires symbol to set leverage")

        session = await self._ensure_session()
        path = "/api/v1/position/updateLeverage"

        body = json.dumps({
            "symbol": symbol.upper(),
            "leverage": int(leverage),
        })

        signature, timestamp, nonce = self._sign_request("POST", path, body)
        url = f"{self.get_base_url()}{path}"

        async with session.post(url, data=body, headers=self._get_headers(signature, timestamp, nonce)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to set leverage: {resp.status}")

    async def _fetch_mark_price(self, symbol: str) -> float | None:
        """Fetch current mark price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/api/v1/mark-price/{symbol.upper()}/current"

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return float(data.get("data", {}).get("markPrice"))
        except Exception:
            return None

    async def _fetch_spot_price(self, symbol: str) -> float | None:
        """Fetch current spot price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/api/v1/market/orderbook/level1"
        params = {"symbol": symbol.upper()}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return float(data.get("data", {}).get("price"))
        except Exception:
            return None

    async def close(self) -> None:
        """Close connections."""
        if self.session:
            await self.session.close()
