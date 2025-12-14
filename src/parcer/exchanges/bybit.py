"""Bybit exchange adapter."""

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


class BybitClient(BaseExchangeClient):
    """Bybit exchange client."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        passphrase: str | None = None,
        sandbox: bool = False,
        proxy: ProxyConfig | None = None,
        **options: Any,
    ):
        super().__init__(
            "bybit",
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
            return "https://api-testnet.bybit.com"
        return "https://api.bybit.com"

    def get_ws_url(self) -> str:
        if self.sandbox:
            return "wss://stream-testnet.bybit.com/v5/public/spot"
        return "wss://stream.bybit.com/v5/public/spot"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            if aiohttp is None:
                raise ImportError("aiohttp is required for Bybit adapter")
            connector = aiohttp.TCPConnector()
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    def _get_headers(self, timestamp: str, signature: str) -> dict[str, str]:
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-SIGN": signature,
            "Content-Type": "application/json",
            "User-Agent": "parcer/1.0",
        }

    def _sign_request(self, method: str, path: str, params: dict[str, Any] | None = None) -> tuple[str, str]:
        """Generate Bybit signature."""
        timestamp = str(int(time.time() * 1000))
        param_str = urlencode(params or {})
        message = timestamp + self.api_key + str(5000) + param_str
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return timestamp, signature

    async def get_balance(self, asset: str | None = None) -> list[Balance] | Balance:
        """Fetch account balance."""
        session = await self._ensure_session()
        path = "/v5/account/wallet-balance"
        params = {"accountType": "SPOT"}
        timestamp, signature = self._sign_request("GET", path, params)
        url = f"{self.get_base_url()}{path}"

        headers = self._get_headers(timestamp, signature)
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch balance: {resp.status}")
            data = await resp.json()

        balances = []
        for coin in data.get("result", {}).get("list", [{}])[0].get("coin", []):
            curr = coin.get("coin")
            free = float(coin.get("walletBalance", 0))
            locked = float(coin.get("lockedInStake", 0))
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
        path = "/v5/order/create"

        params = {
            "category": "spot",
            "symbol": symbol.upper(),
            "side": side.upper(),
            "orderType": "Market",
            "qty": str(quantity),
        }

        timestamp, signature = self._sign_request("POST", path, params)
        url = f"{self.get_base_url()}{path}"
        headers = self._get_headers(timestamp, signature)

        async with session.post(url, json=params, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to place order: {resp.status}")
            data = await resp.json()

        order_data = data.get("result", {})
        return Order(
            order_data.get("orderId"),
            symbol.upper(),
            side.lower(),
            quantity,
            0.0,
            order_data.get("orderStatus", "").lower(),
        )

    async def cancel_order(self, order_id: str, symbol: str | None = None) -> Order:
        """Cancel an active order."""
        if not symbol:
            raise ValueError("Bybit requires symbol to cancel order")

        session = await self._ensure_session()
        path = "/v5/order/cancel"

        params = {
            "category": "spot",
            "symbol": symbol.upper(),
            "orderId": order_id,
        }

        timestamp, signature = self._sign_request("POST", path, params)
        url = f"{self.get_base_url()}{path}"
        headers = self._get_headers(timestamp, signature)

        async with session.post(url, json=params, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to cancel order: {resp.status}")
            data = await resp.json()

        order_data = data.get("result", {})
        return Order(
            order_id,
            symbol.upper(),
            "",
            0,
            0.0,
            order_data.get("orderStatus", "").lower(),
        )

    async def set_leverage(self, leverage: float, symbol: str | None = None) -> None:
        """Set leverage for perpetual trading."""
        if not symbol:
            raise ValueError("Bybit requires symbol to set leverage")

        session = await self._ensure_session()
        path = "/v5/position/set-leverage"

        params = {
            "category": "linear",
            "symbol": symbol.upper(),
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage),
        }

        timestamp, signature = self._sign_request("POST", path, params)
        url = f"{self.get_base_url()}{path}"
        headers = self._get_headers(timestamp, signature)

        async with session.post(url, json=params, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to set leverage: {resp.status}")

    async def _fetch_mark_price(self, symbol: str) -> float | None:
        """Fetch current mark price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/v5/market/mark-price-kline"
        params = {"category": "linear", "symbol": symbol.upper(), "interval": "1"}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                result = data.get("result", {}).get("list", [])
                if result:
                    return float(result[0][1])
                return None
        except Exception:
            return None

    async def _fetch_spot_price(self, symbol: str) -> float | None:
        """Fetch current spot price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/v5/market/tickers"
        params = {"category": "spot", "symbol": symbol.upper()}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return float(data.get("result", {}).get("list", [{}])[0].get("lastPrice"))
        except Exception:
            return None

    async def close(self) -> None:
        """Close connections."""
        if self.session:
            await self.session.close()
