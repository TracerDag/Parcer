"""Tests for exchange client factory."""

import pytest

from parcer.exchanges.factory import create_exchange_client, EXCHANGE_CLIENTS
from parcer.exchanges.binance import BinanceClient
from parcer.exchanges.okx import OKXClient
from parcer.exchanges.bybit import BybitClient


class TestExchangeFactory:
    """Tests for exchange client factory."""

    def test_create_binance_client(self):
        """Test creating Binance client."""
        client = create_exchange_client(
            "binance",
            "test_key",
            "test_secret",
        )
        assert isinstance(client, BinanceClient)
        assert client.api_key == "test_key"

    def test_create_okx_client(self):
        """Test creating OKX client."""
        client = create_exchange_client(
            "okx",
            "test_key",
            "test_secret",
            passphrase="test_passphrase",
        )
        assert isinstance(client, OKXClient)
        assert client.passphrase == "test_passphrase"

    def test_create_bybit_client(self):
        """Test creating Bybit client."""
        client = create_exchange_client(
            "bybit",
            "test_key",
            "test_secret",
        )
        assert isinstance(client, BybitClient)

    def test_sandbox_mode(self):
        """Test creating client in sandbox mode."""
        client = create_exchange_client(
            "binance",
            "test_key",
            "test_secret",
            sandbox=True,
        )
        assert client.sandbox is True
        assert "testnet" in client.get_base_url()

    def test_proxy_configuration(self):
        """Test creating client with proxy."""
        proxy_config = {
            "url": "http://127.0.0.1:8080",
            "username": "user",
            "password": "pass",
        }
        client = create_exchange_client(
            "binance",
            "test_key",
            "test_secret",
            proxy=proxy_config,
        )
        assert client.proxy.url == "http://127.0.0.1:8080"
        assert "user:pass@" in client.proxy.proxy_url

    def test_unsupported_exchange(self):
        """Test error for unsupported exchange."""
        with pytest.raises(ValueError, match="Unsupported exchange"):
            create_exchange_client(
                "invalid_exchange",
                "test_key",
                "test_secret",
            )

    def test_okx_requires_passphrase(self):
        """Test that OKX requires passphrase."""
        with pytest.raises(ValueError, match="requires passphrase"):
            create_exchange_client(
                "okx",
                "test_key",
                "test_secret",
            )

    def test_kucoin_requires_passphrase(self):
        """Test that KuCoin requires passphrase."""
        with pytest.raises(ValueError, match="requires passphrase"):
            create_exchange_client(
                "kucoin",
                "test_key",
                "test_secret",
            )

    def test_bitget_requires_passphrase(self):
        """Test that Bitget requires passphrase."""
        with pytest.raises(ValueError, match="requires passphrase"):
            create_exchange_client(
                "bitget",
                "test_key",
                "test_secret",
            )

    def test_all_exchanges_supported(self):
        """Test that all expected exchanges are in factory."""
        expected = {
            "binance", "okx", "bybit", "bitget", "gate", "kucoin",
            "mexc", "htx", "bingx", "xt"
        }
        assert expected.issubset(EXCHANGE_CLIENTS.keys())

    def test_case_insensitive_exchange_names(self):
        """Test that exchange names are case-insensitive."""
        client1 = create_exchange_client(
            "BINANCE",
            "test_key",
            "test_secret",
        )
        client2 = create_exchange_client(
            "binance",
            "test_key",
            "test_secret",
        )
        assert type(client1) == type(client2)

    def test_additional_options(self):
        """Test passing additional options."""
        client = create_exchange_client(
            "binance",
            "test_key",
            "test_secret",
            recv_window_ms=10000,
        )
        assert client.recv_window_ms == 10000
