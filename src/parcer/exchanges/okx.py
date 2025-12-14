"""OKX exchange adapter."""

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


class OKXClient(BaseExchangeClient):
    """OKX exchange client."""

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
            "okx",
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
            return "https://www.okx.com"
        return "https://www.okx.com"

    def get_ws_url(self) -> str:
        if self.sandbox:
            return "wss://wspap.okx.com:8443/ws/v5/public"
        return "wss://ws.okx.com:8443/ws/v5/public"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            if aiohttp is None:
                raise ImportError("aiohttp is required for OKX adapter")
            connector = aiohttp.TCPConnector()
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    def _get_headers(self, timestamp: str, signature: str) -> dict[str, str]:
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "User-Agent": "parcer/1.0",
        }

    def _sign_request(self, method: str, path: str, body: str = "") -> tuple[str, str]:
        """Generate OKX signature."""
        timestamp = str(int(time.time()))
        message = timestamp + method + path + body
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode(),
                message.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        return timestamp, signature

    async def get_balance(self, asset: str | None = None) -> list[Balance] | Balance:
        """Fetch account balance."""
        session = await self._ensure_session()
        path = "/api/v5/account/balance"
        timestamp, signature = self._sign_request("GET", path)
        url = f"{self.get_base_url()}{path}"

        async with session.get(url, headers=self._get_headers(timestamp, signature)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch balance: {resp.status}")
            data = await resp.json()

        balances = []
        for detail in data.get("data", [{}])[0].get("details", []):
            ccy = detail.get("ccy")
            free = float(detail.get("availBal", 0))
            locked = float(detail.get("frozenBal", 0))
            if free > 0 or locked > 0:
                balances.append(Balance(ccy, free, locked))

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
        path = "/api/v5/trade/order"

        body = json.dumps({
            "instId": symbol.upper(),
            "tdMode": "cash",
            "side": side.lower(),
            "ordType": "market",
            "sz": str(quantity),
        })

        timestamp, signature = self._sign_request("POST", path, body)
        url = f"{self.get_base_url()}{path}"

        async with session.post(url, data=body, headers=self._get_headers(timestamp, signature)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to place order: {resp.status}")
            data = await resp.json()

        order_data = data.get("data", [{}])[0]
        return Order(
            order_data.get("ordId"),
            symbol.upper(),
            side.lower(),
            quantity,
            0.0,
            order_data.get("state", "").lower(),
        )

    async def cancel_order(self, order_id: str, symbol: str | None = None) -> Order:
        """Cancel an active order."""
        if not symbol:
            raise ValueError("OKX requires symbol to cancel order")

        session = await self._ensure_session()
        path = "/api/v5/trade/cancel-order"

        body = json.dumps({
            "ordId": order_id,
            "instId": symbol.upper(),
        })

        timestamp, signature = self._sign_request("POST", path, body)
        url = f"{self.get_base_url()}{path}"

        async with session.post(url, data=body, headers=self._get_headers(timestamp, signature)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to cancel order: {resp.status}")
            data = await resp.json()

        order_data = data.get("data", [{}])[0]
        return Order(
            order_id,
            symbol.upper(),
            "",
            0,
            0.0,
            order_data.get("state", "").lower(),
        )

    async def set_leverage(self, leverage: float, symbol: str | None = None) -> None:
        """Set leverage for perpetual trading."""
        if not symbol:
            raise ValueError("OKX requires symbol to set leverage")

        session = await self._ensure_session()
        path = "/api/v5/account/set-leverage"

        body = json.dumps({
            "lever": int(leverage),
            "mgnMode": "isolated",
            "instId": symbol.upper(),
        })

        timestamp, signature = self._sign_request("POST", path, body)
        url = f"{self.get_base_url()}{path}"

        async with session.post(url, data=body, headers=self._get_headers(timestamp, signature)) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to set leverage: {resp.status}")

    async def _fetch_mark_price(self, symbol: str) -> float | None:
        """Fetch current mark price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/api/v5/public/mark-price"
        params = {"instId": symbol.upper(), "instType": "SWAP"}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return float(data.get("data", [{}])[0].get("markPx"))
        except Exception:
            return None

    async def _fetch_spot_price(self, symbol: str) -> float | None:
        """Fetch current spot price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/api/v5/market/tickers"
        params = {"instId": symbol.upper(), "instType": "SPOT"}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return float(data.get("data", [{}])[0].get("last"))
        except Exception:
            return None

    async def close(self) -> None:
        """Close connections."""
        if self.session:
            await self.session.close()
