"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def api_key():
    """Test API key."""
    return "test_api_key_123456"


@pytest.fixture
def api_secret():
    """Test API secret."""
    return "test_api_secret_789012"


@pytest.fixture
def passphrase():
    """Test passphrase."""
    return "test_passphrase_345678"


@pytest.fixture
def sample_balance_response():
    """Sample balance response data."""
    return {
        "balances": [
            {"asset": "BTC", "free": "0.5", "locked": "0.1"},
            {"asset": "ETH", "free": "10.0", "locked": "2.0"},
            {"asset": "USDT", "free": "1000.0", "locked": "0.0"},
        ]
    }


@pytest.fixture
def sample_order_response():
    """Sample order response data."""
    return {
        "orderId": 123456789,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quantity": "0.5",
        "executedQty": "0.5",
        "status": "FILLED",
        "transactTime": 1234567890000,
    }


@pytest.fixture
def sample_price_response():
    """Sample price response data."""
    return {
        "symbol": "BTCUSDT",
        "price": "45000.00",
        "bid": "44999.50",
        "ask": "45000.50",
    }
