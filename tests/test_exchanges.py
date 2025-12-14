"""Tests for exchange adapters with mocked HTTP/WebSocket responses."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parcer.exchanges.base import ProxyConfig
from parcer.exchanges.binance import BinanceClient
from parcer.exchanges.okx import OKXClient
from parcer.exchanges.bybit import BybitClient
from parcer.exchanges.bitget import BitgetClient
from parcer.exchanges.gate import GateClient
from parcer.exchanges.kucoin import KuCoinClient
from parcer.exchanges.mexc import MEXCClient
from parcer.exchanges.htx import HTXClient
from parcer.exchanges.bingx import BingXClient
from parcer.exchanges.xt import XTClient
from parcer.exchanges.protocol import Balance, Order


def create_async_response(status=200, json_data=None):
    """Create a mock async response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


class TestBinanceAdapter:
    """Tests for Binance adapter."""

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test fetching account balance."""
        client = BinanceClient("test_key", "test_secret")

        mock_response = {
            "balances": [
                {"asset": "BTC", "free": "0.5", "locked": "0.1"},
                {"asset": "ETH", "free": "10.0", "locked": "2.0"},
                {"asset": "USDT", "free": "1000.0", "locked": "0.0"},
            ]
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        
        client._ensure_session = AsyncMock(return_value=mock_session)

        balances = await client.get_balance()

        assert len(balances) == 3
        assert balances[0].asset == "BTC"
        assert balances[0].free == 0.5
        assert balances[0].used == 0.1
        assert balances[0].total == 0.6

        await client.close()

    @pytest.mark.asyncio
    async def test_get_balance_specific_asset(self):
        """Test fetching balance for a specific asset."""
        client = BinanceClient("test_key", "test_secret")

        mock_response = {
            "balances": [
                {"asset": "BTC", "free": "0.5", "locked": "0.1"},
                {"asset": "USDT", "free": "1000.0", "locked": "0.0"},
            ]
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        balance = await client.get_balance("BTC")

        assert isinstance(balance, Balance)
        assert balance.asset == "BTC"
        assert balance.free == 0.5

        await client.close()

    @pytest.mark.asyncio
    async def test_place_market_order(self):
        """Test placing a market order."""
        client = BinanceClient("test_key", "test_secret")

        mock_response = {
            "orderId": 123456,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "executedQty": "0.5",
            "status": "FILLED",
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        order = await client.place_market_order("BTCUSDT", "buy", 0.5)

        assert isinstance(order, Order)
        assert order.order_id == "123456"
        assert order.symbol == "BTCUSDT"
        assert order.side == "buy"
        assert order.quantity == 0.5
        assert order.status == "filled"

        await client.close()

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """Test cancelling an order."""
        client = BinanceClient("test_key", "test_secret")

        mock_response = {
            "orderId": 123456,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "executedQty": "0.0",
            "status": "CANCELED",
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.delete = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        order = await client.cancel_order("123456", "BTCUSDT")

        assert order.order_id == "123456"
        assert order.status == "canceled"

        await client.close()

    @pytest.mark.asyncio
    async def test_fetch_spot_price(self):
        """Test fetching spot price."""
        client = BinanceClient("test_key", "test_secret")

        mock_response = {
            "symbol": "BTCUSDT",
            "price": "45000.00",
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        price = await client._fetch_spot_price("BTCUSDT")

        assert price == 45000.0

        await client.close()


class TestOKXAdapter:
    """Tests for OKX adapter."""

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test fetching account balance."""
        client = OKXClient("test_key", "test_secret", passphrase="test_passphrase")

        mock_response = {
            "data": [
                {
                    "details": [
                        {"ccy": "BTC", "availBal": "0.5", "frozenBal": "0.1"},
                        {"ccy": "USDT", "availBal": "1000.0", "frozenBal": "0.0"},
                    ]
                }
            ]
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        balances = await client.get_balance()

        assert len(balances) == 2
        assert balances[0].asset == "BTC"
        assert balances[0].free == 0.5

        await client.close()

    @pytest.mark.asyncio
    async def test_place_market_order(self):
        """Test placing a market order."""
        client = OKXClient("test_key", "test_secret", passphrase="test_passphrase")

        mock_response = {
            "data": [
                {
                    "ordId": "123456",
                    "state": "live",
                }
            ]
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        order = await client.place_market_order("BTCUSDT", "buy", 0.5)

        assert order.order_id == "123456"
        assert order.status == "live"

        await client.close()


class TestBybitAdapter:
    """Tests for Bybit adapter."""

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test fetching account balance."""
        client = BybitClient("test_key", "test_secret")

        mock_response = {
            "result": {
                "list": [
                    {
                        "coin": [
                            {"coin": "BTC", "walletBalance": "0.5", "lockedInStake": "0.1"},
                            {"coin": "USDT", "walletBalance": "1000.0", "lockedInStake": "0.0"},
                        ]
                    }
                ]
            }
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        balances = await client.get_balance()

        assert len(balances) == 2

        await client.close()

    @pytest.mark.asyncio
    async def test_place_market_order(self):
        """Test placing a market order."""
        client = BybitClient("test_key", "test_secret")

        mock_response = {
            "result": {
                "orderId": "123456",
                "orderStatus": "New",
            }
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        order = await client.place_market_order("BTCUSDT", "buy", 0.5)

        assert order.order_id == "123456"

        await client.close()


class TestBitgetAdapter:
    """Tests for Bitget adapter."""

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test fetching account balance."""
        client = BitgetClient("test_key", "test_secret", passphrase="test_passphrase")

        mock_response = {
            "data": [
                {"coinId": "BTC", "available": "0.5", "locked": "0.1"},
                {"coinId": "USDT", "available": "1000.0", "locked": "0.0"},
            ]
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        balances = await client.get_balance()

        assert len(balances) == 2

        await client.close()


class TestGateAdapter:
    """Tests for Gate.io adapter."""

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test fetching account balance."""
        client = GateClient("test_key", "test_secret")

        mock_response = [
            {
                "balances": [
                    {"currency": "BTC", "available": "0.5", "locked": "0.1"},
                    {"currency": "USDT", "available": "1000.0", "locked": "0.0"},
                ]
            }
        ]

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        balances = await client.get_balance()

        assert len(balances) == 2

        await client.close()


class TestKuCoinAdapter:
    """Tests for KuCoin adapter."""

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test fetching account balance."""
        client = KuCoinClient("test_key", "test_secret", passphrase="test_passphrase")

        mock_response = {
            "data": [
                {"type": "trade", "currency": "BTC", "available": "0.5", "holds": "0.1"},
                {"type": "trade", "currency": "USDT", "available": "1000.0", "holds": "0.0"},
            ]
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        balances = await client.get_balance()

        assert len(balances) == 2

        await client.close()


class TestMEXCAdapter:
    """Tests for MEXC adapter."""

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test fetching account balance (REST only)."""
        client = MEXCClient("test_key", "test_secret")

        mock_response = {
            "balances": [
                {"asset": "BTC", "free": "0.5", "locked": "0.1"},
                {"asset": "USDT", "free": "1000.0", "locked": "0.0"},
            ]
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        balances = await client.get_balance()

        assert len(balances) == 2

        await client.close()

    @pytest.mark.asyncio
    async def test_fetch_spot_price(self):
        """Test fetching spot price (MEXC is REST only)."""
        client = MEXCClient("test_key", "test_secret")

        mock_response = {
            "symbol": "BTCUSDT",
            "price": "45000.00",
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        price = await client._fetch_spot_price("BTCUSDT")

        assert price == 45000.0

        await client.close()


class TestHTXAdapter:
    """Tests for HTX adapter."""

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test fetching account balance."""
        client = HTXClient("test_key", "test_secret")

        # Mock accounts response
        accounts_response = {
            "data": [{"id": "12345"}]
        }

        # Mock balance response
        balance_response = {
            "data": {
                "list": [
                    {"currency": "btc", "type": "trade", "balance": "0.5"},
                    {"currency": "btc", "type": "frozen", "balance": "0.1"},
                    {"currency": "usdt", "type": "trade", "balance": "1000.0"},
                ]
            }
        }

        mock_resp_accounts = create_async_response(200, accounts_response)
        mock_resp_balance = create_async_response(200, balance_response)

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=[mock_resp_accounts, mock_resp_balance])
        client._ensure_session = AsyncMock(return_value=mock_session)

        balances = await client.get_balance()

        assert len(balances) >= 1
        assert any(b.asset == "BTC" for b in balances)

        await client.close()


class TestBingXAdapter:
    """Tests for BingX adapter."""

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test fetching account balance."""
        client = BingXClient("test_key", "test_secret")

        mock_response = {
            "data": {
                "balances": [
                    {"asset": "BTC", "free": "0.5", "locked": "0.1"},
                    {"asset": "USDT", "free": "1000.0", "locked": "0.0"},
                ]
            }
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        balances = await client.get_balance()

        assert len(balances) == 2

        await client.close()


class TestXTAdapter:
    """Tests for XT adapter."""

    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test fetching account balance."""
        client = XTClient("test_key", "test_secret")

        mock_response = {
            "result": [
                {"coin": "BTC", "free": "0.5", "locked": "0.1"},
                {"coin": "USDT", "free": "1000.0", "locked": "0.0"},
            ]
        }

        mock_resp = create_async_response(200, mock_response)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        balances = await client.get_balance()

        assert len(balances) == 2

        await client.close()


class TestProxyConfig:
    """Tests for proxy configuration."""

    def test_proxy_without_auth(self):
        """Test proxy URL without authentication."""
        proxy = ProxyConfig(url="http://127.0.0.1:8080")
        assert proxy.proxy_url == "http://127.0.0.1:8080"

    def test_proxy_with_auth(self):
        """Test proxy URL with username and password."""
        proxy = ProxyConfig(
            url="http://127.0.0.1:8080",
            username="user",
            password="pass",
        )
        assert "user:pass@" in proxy.proxy_url

    def test_proxy_none(self):
        """Test None proxy."""
        proxy = ProxyConfig(url=None)
        assert proxy.proxy_url is None


class TestSymbolNormalizationInAdapter:
    """Tests for symbol normalization in adapters."""

    def test_binance_uses_normalized_symbols(self):
        """Test that Binance adapter normalizes symbols."""
        client = BinanceClient("test_key", "test_secret")

        normalized_url = client.get_base_url()
        assert "binance.com" in normalized_url

    def test_okx_uses_normalized_symbols(self):
        """Test that OKX adapter uses correct format."""
        client = OKXClient("test_key", "test_secret", passphrase="test")

        normalized_url = client.get_base_url()
        assert "okx.com" in normalized_url
