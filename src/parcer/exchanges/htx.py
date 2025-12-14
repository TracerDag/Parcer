"""HTX (Huobi) exchange adapter."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import urlencode
import base64

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:
    aiohttp = None

from .base import BaseExchangeClient, ProxyConfig
from .protocol import Balance, Order


class HTXClient(BaseExchangeClient):
    """HTX (Huobi) exchange client."""

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
            "htx",
            api_key,
            api_secret,
            sandbox=sandbox,
            proxy=proxy,
            **options,
        )
        self.session = None
        self.account_id = None

    def get_base_url(self) -> str:
        if self.sandbox:
            return "https://api.huobi.pro"
        return "https://api.huobi.pro"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            if aiohttp is None:
                raise ImportError("aiohttp is required for HTX adapter")
            connector = aiohttp.TCPConnector()
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    def _get_signature(self, method: str, path: str, params: dict[str, Any]) -> str:
        """Generate HTX signature."""
        payload = "\n".join([method, "api.huobi.pro", path])
        sorted_params = sorted(params.items())
        for key, value in sorted_params:
            payload += f"\n{key}={value}"

        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode(),
                payload.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        return signature

    async def get_balance(self, asset: str | None = None) -> list[Balance] | Balance:
        """Fetch account balance."""
        session = await self._ensure_session()
        path = "/v1/account/accounts"
        params = {
            "AccessKeyId": self.api_key,
            "SignatureMethod": "HmacSHA256",
            "SignatureVersion": "2",
            "Timestamp": int(time.time()),
        }
        signature = self._get_signature("GET", path, params)
        params["Signature"] = signature

        url = f"{self.get_base_url()}{path}"
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch accounts: {resp.status}")
            data = await resp.json()

        accounts = data.get("data", [])
        if accounts:
            self.account_id = accounts[0]["id"]

        if not self.account_id:
            raise Exception("No account ID found")

        path = f"/v1/account/accounts/{self.account_id}/balance"
        params = {
            "AccessKeyId": self.api_key,
            "SignatureMethod": "HmacSHA256",
            "SignatureVersion": "2",
            "Timestamp": int(time.time()),
        }
        signature = self._get_signature("GET", path, params)
        params["Signature"] = signature

        url = f"{self.get_base_url()}{path}"
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch balance: {resp.status}")
            data = await resp.json()

        balances = []
        for list_item in data.get("data", {}).get("list", []):
            curr = list_item.get("currency").upper()
            balance_type = list_item.get("type")
            amount = float(list_item.get("balance", 0))

            if balance_type == "trade":
                free = amount
                locked = 0
            elif balance_type == "frozen":
                free = 0
                locked = amount
            else:
                continue

            if free > 0 or locked > 0:
                existing = next((b for b in balances if b.asset == curr), None)
                if existing:
                    existing.free += free
                    existing.used += locked
                else:
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

        if not self.account_id:
            await self.get_balance()

        path = "/v1/order/orders/place"
        body = {
            "account-id": str(self.account_id),
            "symbol": symbol.lower(),
            "type": f"{side.lower()}-market",
            "amount": str(quantity),
        }

        params = {
            "AccessKeyId": self.api_key,
            "SignatureMethod": "HmacSHA256",
            "SignatureVersion": "2",
            "Timestamp": int(time.time()),
        }
        signature = self._get_signature("POST", path, params)
        params["Signature"] = signature

        url = f"{self.get_base_url()}{path}"
        async with session.post(url, json=body, params=params) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to place order: {resp.status}")
            data = await resp.json()

        order_id = data.get("data")
        return Order(
            str(order_id),
            symbol.upper(),
            side.lower(),
            quantity,
            0.0,
            "submitted",
        )

    async def cancel_order(self, order_id: str, symbol: str | None = None) -> Order:
        """Cancel an active order."""
        session = await self._ensure_session()
        path = f"/v1/order/orders/{order_id}/submitcancel"

        params = {
            "AccessKeyId": self.api_key,
            "SignatureMethod": "HmacSHA256",
            "SignatureVersion": "2",
            "Timestamp": int(time.time()),
        }
        signature = self._get_signature("POST", path, params)
        params["Signature"] = signature

        url = f"{self.get_base_url()}{path}"
        async with session.post(url, params=params) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to cancel order: {resp.status}")
            data = await resp.json()

        return Order(
            order_id,
            symbol or "",
            "",
            0,
            0.0,
            "cancelling",
        )

    async def _fetch_spot_price(self, symbol: str) -> float | None:
        """Fetch current spot price."""
        session = await self._ensure_session()
        url = f"{self.get_base_url()}/market/trade"
        params = {"symbol": symbol.lower()}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                tick = data.get("tick", {})
                trades = tick.get("data", [])
                if trades:
                    return float(trades[0].get("price"))
                return None
        except Exception:
            return None

    async def close(self) -> None:
        """Close connections."""
        if self.session:
            await self.session.close()
