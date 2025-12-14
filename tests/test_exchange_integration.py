"""Integration tests for exchange adapters."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parcer.exchanges import (
    create_exchange_client,
    normalize_symbol,
    check_symbol_mismatch,
)
from parcer.exchanges.protocol import Balance, Order


def create_async_response(status=200, json_data=None):
    """Create a mock async response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


class TestExchangeIntegration:
    """Integration tests for exchange adapters."""

    @pytest.mark.asyncio
    async def test_complete_binance_workflow(self):
        """Test complete Binance workflow: balance -> order -> cancel."""
        client = create_exchange_client(
            "binance",
            "test_key",
            "test_secret",
        )

        balance_response = {
            "balances": [
                {"asset": "BTC", "free": "1.0", "locked": "0.0"},
                {"asset": "USDT", "free": "10000.0", "locked": "0.0"},
            ]
        }

        order_response = {
            "orderId": 123456,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "executedQty": "0.5",
            "status": "FILLED",
        }

        cancel_response = {
            "orderId": 123456,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "executedQty": "0.5",
            "status": "CANCELED",
        }

        mock_resp_balance = create_async_response(200, balance_response)
        mock_resp_order = create_async_response(200, order_response)
        mock_resp_cancel = create_async_response(200, cancel_response)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp_balance)
        mock_session.post = MagicMock(return_value=mock_resp_order)
        mock_session.delete = MagicMock(return_value=mock_resp_cancel)

        client._ensure_session = AsyncMock(return_value=mock_session)

        # Get balance
        balances = await client.get_balance()
        assert len(balances) == 2

        # Check symbol normalization
        symbol = normalize_symbol("btcusdt")
        assert symbol == "BTCUSDT"

        # Place order
        order = await client.place_market_order(symbol, "buy", 0.5)
        assert order.order_id == "123456"
        assert order.status == "filled"

        # Check symbol match before trade
        assert check_symbol_mismatch(symbol, "BTCUSDT") is True

        # Cancel order
        cancelled = await client.cancel_order("123456", symbol)
        assert cancelled.status == "canceled"

        await client.close()

    @pytest.mark.asyncio
    async def test_symbol_mismatch_logging(self):
        """Test symbol mismatch logging."""
        logged_messages = []

        def mock_logger(msg):
            logged_messages.append(msg)

        # Test mismatch
        result = check_symbol_mismatch(
            "BTCUSDT",
            "ETHUSDT",
            logger_func=mock_logger,
        )
        assert result is False
        assert len(logged_messages) == 1
        assert "Symbol mismatch" in logged_messages[0]

        # Test match
        logged_messages.clear()
        result = check_symbol_mismatch(
            "BTC-USDT",
            "BTC/USDT",
            logger_func=mock_logger,
        )
        assert result is True
        assert len(logged_messages) == 0

    @pytest.mark.asyncio
    async def test_multi_exchange_symbol_normalization(self):
        """Test symbol normalization across exchanges."""
        symbols = {
            "binance": "BTCUSDT",
            "okx": "BTC-USDT",
            "bybit": "BTCUSDT",
            "gate": "BTC-USDT",
            "kucoin": "BTC-USDT",
        }

        for exchange, symbol in symbols.items():
            normalized = normalize_symbol(symbol)
            assert normalized == "BTCUSDT", f"{exchange} symbol {symbol} normalized to {normalized}"

    @pytest.mark.asyncio
    async def test_balance_with_symbol_verification(self):
        """Test balance fetch with symbol verification."""
        client = create_exchange_client(
            "binance",
            "test_key",
            "test_secret",
        )

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

        for balance in balances:
            assert isinstance(balance, Balance)
            assert balance.asset in ["BTC", "USDT"]
            assert balance.total == balance.free + balance.used

        await client.close()

    @pytest.mark.asyncio
    async def test_order_with_normalized_symbol(self):
        """Test placing order with symbol normalization."""
        client = create_exchange_client(
            "binance",
            "test_key",
            "test_secret",
        )

        response = {
            "orderId": 999,
            "symbol": "BTCUSDT",
            "side": "SELL",
            "executedQty": "1.0",
            "status": "FILLED",
        }

        mock_resp = create_async_response(200, response)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        client._ensure_session = AsyncMock(return_value=mock_session)

        order = await client.place_market_order(
            normalize_symbol("btc-usdt"),
            "sell",
            1.0
        )

        assert isinstance(order, Order)
        assert order.symbol == "BTCUSDT"

        await client.close()

    @pytest.mark.asyncio
    async def test_okx_with_passphrase(self):
        """Test OKX client requiring passphrase."""
        client = create_exchange_client(
            "okx",
            "test_key",
            "test_secret",
            passphrase="test_passphrase",
        )

        assert client.passphrase == "test_passphrase"
        assert client.name == "okx"

    @pytest.mark.asyncio
    async def test_proxy_auth_configuration(self):
        """Test proxy authentication configuration."""
        proxy_config = {
            "url": "http://proxy.example.com:8080",
            "username": "proxy_user",
            "password": "proxy_pass",
        }

        client = create_exchange_client(
            "binance",
            "test_key",
            "test_secret",
            proxy=proxy_config,
        )

        assert client.proxy.url == "http://proxy.example.com:8080"
        assert client.proxy.username == "proxy_user"
        proxy_url = client.proxy.proxy_url
        assert "proxy_user:proxy_pass@" in proxy_url

    @pytest.mark.asyncio
    async def test_sandbox_mode_urls(self):
        """Test that sandbox mode uses correct URLs."""
        exchanges = ["binance", "okx", "bybit", "kucoin"]

        for exchange in exchanges:
            kwargs = {}
            if exchange in {"okx", "kucoin"}:
                kwargs["passphrase"] = "test"

            client = create_exchange_client(
                exchange,
                "test_key",
                "test_secret",
                sandbox=True,
                **kwargs,
            )

            base_url = client.get_base_url()
            assert isinstance(base_url, str)
            assert "http" in base_url


class TestExchangeClientCreation:
    """Tests for exchange client creation."""

    def test_all_exchanges_can_be_created(self):
        """Test that all exchanges can be created."""
        base_kwargs = {
            "api_key": "test",
            "api_secret": "test",
        }

        exchanges_with_passphrase = {"okx", "kucoin", "bitget"}
        exchanges_without_passphrase = {
            "binance", "bybit", "gate", "mexc", "htx", "bingx", "xt"
        }

        for exchange in exchanges_without_passphrase:
            client = create_exchange_client(exchange, **base_kwargs)
            assert client.api_key == "test"

        for exchange in exchanges_with_passphrase:
            kwargs = {**base_kwargs, "passphrase": "test"}
            client = create_exchange_client(exchange, **kwargs)
            assert client.passphrase == "test"
