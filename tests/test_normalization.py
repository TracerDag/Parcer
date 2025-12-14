"""Tests for symbol normalization utilities."""

import pytest

from parcer.exchanges.normalization import (
    check_symbol_mismatch,
    extract_base_symbol,
    normalize_symbol,
)


class TestNormalizeSymbol:
    """Tests for normalize_symbol function."""

    def test_unified_format(self):
        """Test conversion to unified format (BTCUSDT)."""
        assert normalize_symbol("BTCUSDT", "unified") == "BTCUSDT"
        assert normalize_symbol("BTC-USDT", "unified") == "BTCUSDT"
        assert normalize_symbol("BTC/USDT", "unified") == "BTCUSDT"

    def test_hyphen_format(self):
        """Test conversion to hyphen format (BTC-USDT)."""
        assert normalize_symbol("BTCUSDT", "hyphen") == "BTC-USDT"
        assert normalize_symbol("BTC-USDT", "hyphen") == "BTC-USDT"
        assert normalize_symbol("BTC/USDT", "hyphen") == "BTC-USDT"

    def test_slash_format(self):
        """Test conversion to slash format (BTC/USDT)."""
        assert normalize_symbol("BTCUSDT", "slash") == "BTC/USDT"
        assert normalize_symbol("BTC-USDT", "slash") == "BTC/USDT"
        assert normalize_symbol("BTC/USDT", "slash") == "BTC/USDT"

    def test_case_insensitive(self):
        """Test that normalization is case-insensitive."""
        assert normalize_symbol("btcusdt") == "BTCUSDT"
        assert normalize_symbol("btc-usdt") == "BTCUSDT"

    def test_whitespace_stripped(self):
        """Test that whitespace is stripped."""
        assert normalize_symbol("  BTCUSDT  ") == "BTCUSDT"
        assert normalize_symbol("  BTC - USDT  ") == "BTCUSDT"

    def test_multiple_stablecoins(self):
        """Test symbols with multiple stablecoin suffixes."""
        assert normalize_symbol("ETHUSDC", "unified") == "ETHUSDC"
        assert normalize_symbol("ETHBUSD", "unified") == "ETHBUSD"


class TestExtractBaseSymbol:
    """Tests for extract_base_symbol function."""

    def test_hyphen_separated(self):
        """Test extraction from hyphen-separated symbols."""
        assert extract_base_symbol("BTC-USDT") == ("BTC", "USDT")
        assert extract_base_symbol("ETH-USDC") == ("ETH", "USDC")

    def test_slash_separated(self):
        """Test extraction from slash-separated symbols."""
        assert extract_base_symbol("BTC/USDT") == ("BTC", "USDT")
        assert extract_base_symbol("ETH/USDC") == ("ETH", "USDC")

    def test_unified_format(self):
        """Test extraction from unified format (BTCUSDT)."""
        assert extract_base_symbol("BTCUSDT") == ("BTC", "USDT")
        assert extract_base_symbol("ETHUSDC") == ("ETH", "USDC")
        assert extract_base_symbol("BTCBUSD") == ("BTC", "BUSD")

    def test_single_currency(self):
        """Test extraction from single currency."""
        assert extract_base_symbol("BTC") == ("BTC", "")
        assert extract_base_symbol("ETH") == ("ETH", "")

    def test_stablecoin_priority(self):
        """Test that stablecoins are correctly identified."""
        base, quote = extract_base_symbol("BTCUSDT")
        assert quote == "USDT"

        base, quote = extract_base_symbol("ETHUSDC")
        assert quote == "USDC"

    def test_case_insensitive(self):
        """Test case insensitivity."""
        assert extract_base_symbol("btcusdt") == ("BTC", "USDT")
        assert extract_base_symbol("btc-usdt") == ("BTC", "USDT")

    def test_empty_symbol(self):
        """Test empty symbol."""
        assert extract_base_symbol("") == ("", "")


class TestCheckSymbolMismatch:
    """Tests for check_symbol_mismatch function."""

    def test_matching_symbols(self):
        """Test that matching symbols return True."""
        assert check_symbol_mismatch("BTCUSDT", "BTCUSDT") is True
        assert check_symbol_mismatch("BTCUSDT", "BTC-USDT") is True
        assert check_symbol_mismatch("BTCUSDT", "BTC/USDT") is True

    def test_mismatched_symbols(self):
        """Test that mismatched symbols return False."""
        assert check_symbol_mismatch("BTCUSDT", "ETHUSDT") is False
        assert check_symbol_mismatch("BTC-USDT", "ETH-USDT") is False

    def test_custom_logger(self):
        """Test with custom logger function."""
        logged = []

        def mock_logger(msg):
            logged.append(msg)

        result = check_symbol_mismatch("BTCUSDT", "ETHUSDT", logger_func=mock_logger)

        assert result is False
        assert len(logged) == 1
        assert "Symbol mismatch" in logged[0]

    def test_matching_with_custom_logger(self):
        """Test matching symbols with custom logger."""
        logged = []

        def mock_logger(msg):
            logged.append(msg)

        result = check_symbol_mismatch("BTCUSDT", "BTC-USDT", logger_func=mock_logger)

        assert result is True
        assert len(logged) == 0


class TestNormalizationIntegration:
    """Integration tests for normalization."""

    def test_round_trip_conversion(self):
        """Test that symbols can be converted between formats."""
        symbols = ["BTCUSDT", "BTC-USDT", "BTC/USDT"]

        for symbol in symbols:
            normalized = normalize_symbol(symbol, "unified")
            assert normalized == "BTCUSDT"

    def test_base_symbol_extraction(self):
        """Test extracting base symbol from various formats."""
        symbols = ["BTCUSDT", "BTC-USDT", "BTC/USDT"]

        for symbol in symbols:
            base, quote = extract_base_symbol(symbol)
            assert base == "BTC"
            assert quote == "USDT"
