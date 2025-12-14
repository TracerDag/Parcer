"""Exchange adapters and connectivity layer."""

from .protocol import ExchangeClient, Balance, Order, PriceUpdate
from .normalization import normalize_symbol, extract_base_symbol, check_symbol_mismatch
from .factory import create_exchange_client, EXCHANGE_CLIENTS
from .base import BaseExchangeClient, ProxyConfig

__all__ = [
    "ExchangeClient",
    "Balance",
    "Order",
    "PriceUpdate",
    "normalize_symbol",
    "extract_base_symbol",
    "check_symbol_mismatch",
    "create_exchange_client",
    "EXCHANGE_CLIENTS",
    "BaseExchangeClient",
    "ProxyConfig",
]
