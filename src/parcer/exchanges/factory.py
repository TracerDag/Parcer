"""Factory for creating exchange client instances."""

from __future__ import annotations

from typing import Any, Type

from .base import BaseExchangeClient, ProxyConfig
from .binance import BinanceClient
from .okx import OKXClient
from .bybit import BybitClient
from .bitget import BitgetClient
from .gate import GateClient
from .kucoin import KuCoinClient
from .mexc import MEXCClient
from .htx import HTXClient
from .bingx import BingXClient
from .xt import XTClient


EXCHANGE_CLIENTS: dict[str, Type[BaseExchangeClient]] = {
    "binance": BinanceClient,
    "okx": OKXClient,
    "bybit": BybitClient,
    "bitget": BitgetClient,
    "gate": GateClient,
    "kucoin": KuCoinClient,
    "mexc": MEXCClient,
    "htx": HTXClient,
    "bingx": BingXClient,
    "xt": XTClient,
}


def create_exchange_client(
    exchange: str,
    api_key: str,
    api_secret: str,
    *,
    passphrase: str | None = None,
    sandbox: bool = False,
    proxy: dict[str, Any] | None = None,
    **options: Any,
) -> BaseExchangeClient:
    """Create an exchange client instance.

    Args:
        exchange: Exchange name (binance, okx, bybit, etc.)
        api_key: API key
        api_secret: API secret
        passphrase: API passphrase (required for OKX, KuCoin, Bitget)
        sandbox: Use sandbox/testnet environment
        proxy: Proxy configuration (url, username, password)
        **options: Additional exchange-specific options

    Returns:
        Configured exchange client

    Raises:
        ValueError: If exchange is not supported
        ValueError: If required parameters are missing
    """
    exchange_lower = exchange.lower()

    if exchange_lower not in EXCHANGE_CLIENTS:
        supported = ", ".join(EXCHANGE_CLIENTS.keys())
        raise ValueError(
            f"Unsupported exchange: {exchange}. Supported exchanges: {supported}"
        )

    client_class = EXCHANGE_CLIENTS[exchange_lower]

    proxy_config = None
    if proxy:
        proxy_config = ProxyConfig(
            url=proxy.get("url"),
            username=proxy.get("username"),
            password=proxy.get("password"),
        )

    requires_passphrase = exchange_lower in {"okx", "kucoin", "bitget"}
    if requires_passphrase and not passphrase:
        raise ValueError(f"{exchange} requires passphrase parameter")

    kwargs = {
        "api_key": api_key,
        "api_secret": api_secret,
        "sandbox": sandbox,
        "proxy": proxy_config,
    }

    if passphrase is not None:
        kwargs["passphrase"] = passphrase

    kwargs.update(options)

    return client_class(**kwargs)
