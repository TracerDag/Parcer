"""Tests for spread detection engine."""

import pytest

from parcer.strategy.spread_engine import (
    SpreadDetectionEngine,
    PriceType,
    PricePoint,
)


class TestSpreadDetectionEngine:
    """Tests for spread detection and calculation."""

    def test_update_and_get_price(self):
        """Test price caching."""
        engine = SpreadDetectionEngine()
        engine.update_price("binance", "BTCUSDT", 45000.0)
        assert engine.get_price("binance", "BTCUSDT") == 45000.0

    def test_get_nonexistent_price(self):
        """Test getting price that doesn't exist."""
        engine = SpreadDetectionEngine()
        assert engine.get_price("binance", "ETHUSDT") is None

    def test_calculate_spread_premium_base(self):
        """Test spread calculation with premium base."""
        engine = SpreadDetectionEngine()
        spread = engine.calculate_spread(50000.0, 45000.0, premium_base=True)
        expected = (50000.0 - 45000.0) / 45000.0
        assert abs(spread - expected) < 1e-10

    def test_calculate_spread_discount_base(self):
        """Test spread calculation with discount base."""
        engine = SpreadDetectionEngine()
        spread = engine.calculate_spread(50000.0, 45000.0, premium_base=False)
        expected = (45000.0 - 50000.0) / 50000.0
        assert abs(spread - expected) < 1e-10

    def test_calculate_spread_zero_price(self):
        """Test spread calculation with zero price."""
        engine = SpreadDetectionEngine()
        spread = engine.calculate_spread(0.0, 45000.0, premium_base=True)
        assert spread == 0.0

    def test_detect_scenario_a_spread_positive(self):
        """Test scenario A spread with futures premium."""
        engine = SpreadDetectionEngine()
        calc = engine.detect_scenario_a_spread(50000.0, 45000.0)
        assert calc.spread == pytest.approx((50000.0 - 45000.0) / 45000.0)
        assert calc.premium_exchange == "futures"
        assert calc.discount_exchange == "spot"
        assert calc.price_premium == 50000.0
        assert calc.price_discount == 45000.0

    def test_detect_scenario_a_spread_negative(self):
        """Test scenario A spread with spot premium."""
        engine = SpreadDetectionEngine()
        calc = engine.detect_scenario_a_spread(45000.0, 50000.0)
        assert calc.spread == pytest.approx((45000.0 - 50000.0) / 50000.0)
        assert calc.premium_exchange == "spot"
        assert calc.discount_exchange == "futures"
        assert calc.price_premium == 50000.0
        assert calc.price_discount == 45000.0

    def test_detect_scenario_b_spread(self):
        """Test scenario B spread detection."""
        engine = SpreadDetectionEngine()
        calc = engine.detect_scenario_b_spread(
            45000.0, 50000.0, exchange_a="Binance", exchange_b="Bybit"
        )
        expected_spread = (50000.0 - 45000.0) / 45000.0
        assert calc.spread == pytest.approx(expected_spread)
        assert calc.premium_exchange == "Bybit"
        assert calc.discount_exchange == "Binance"
        assert calc.price_premium == 50000.0
        assert calc.price_discount == 45000.0

    def test_detect_scenario_b_spread_reversed(self):
        """Test scenario B spread with reversed prices."""
        engine = SpreadDetectionEngine()
        calc = engine.detect_scenario_b_spread(
            50000.0, 45000.0, exchange_a="Binance", exchange_b="Bybit"
        )
        expected_spread = (50000.0 - 45000.0) / 45000.0
        assert calc.spread == pytest.approx(expected_spread)
        assert calc.premium_exchange == "Binance"
        assert calc.discount_exchange == "Bybit"
        assert calc.price_premium == 50000.0
        assert calc.price_discount == 45000.0

    def test_check_entry_condition_scenario_a(self):
        """Test entry condition for scenario A."""
        engine = SpreadDetectionEngine()
        assert engine.check_entry_condition(0.05, 0.05, scenario="a")
        assert engine.check_entry_condition(0.06, 0.05, scenario="a")
        assert not engine.check_entry_condition(0.04, 0.05, scenario="a")

    def test_check_entry_condition_scenario_b(self):
        """Test entry condition for scenario B."""
        engine = SpreadDetectionEngine()
        assert engine.check_entry_condition(0.07, 0.07, scenario="b")
        assert engine.check_entry_condition(0.08, 0.07, scenario="b")
        assert not engine.check_entry_condition(0.06, 0.07, scenario="b")

    def test_check_exit_condition_scenario_a(self):
        """Test exit condition for scenario A."""
        engine = SpreadDetectionEngine()
        assert engine.check_exit_condition(0.01, 0.01, scenario="a")
        assert engine.check_exit_condition(0.005, 0.01, scenario="a")
        assert not engine.check_exit_condition(0.02, 0.01, scenario="a")

    def test_check_exit_condition_scenario_b(self):
        """Test exit condition for scenario B."""
        engine = SpreadDetectionEngine()
        assert engine.check_exit_condition(0.01, 0.01, scenario="b")
        assert engine.check_exit_condition(0.005, 0.01, scenario="b")
        assert not engine.check_exit_condition(0.02, 0.01, scenario="b")

    def test_negative_spread_entry_condition(self):
        """Test entry condition with negative spread."""
        engine = SpreadDetectionEngine()
        assert engine.check_entry_condition(-0.05, 0.05, scenario="a")
        assert engine.check_entry_condition(-0.07, 0.07, scenario="b")

    def test_negative_spread_exit_condition(self):
        """Test exit condition with negative spread."""
        engine = SpreadDetectionEngine()
        assert engine.check_exit_condition(-0.01, 0.01, scenario="a")
        assert engine.check_exit_condition(-0.01, 0.01, scenario="b")

    def test_synthetic_price_stream_scenario_a(self):
        """Test price updates with synthetic stream."""
        engine = SpreadDetectionEngine()
        futures_prices = [50000.0, 50100.0, 50050.0, 45000.0]
        spot_prices = [45000.0, 45050.0, 45100.0, 45000.0]

        for futures, spot in zip(futures_prices, spot_prices):
            engine.update_price("binance_futures", "BTCUSDT", futures)
            engine.update_price("binance_spot", "BTCUSDT", spot)

            calc = engine.detect_scenario_a_spread(futures, spot)
            spread = calc.spread

            if futures > spot:
                assert calc.premium_exchange == "futures"
            else:
                assert calc.premium_exchange == "spot"

    def test_synthetic_price_stream_scenario_b(self):
        """Test price updates with synthetic stream."""
        engine = SpreadDetectionEngine()
        exchange_a_prices = [45000.0, 45100.0, 45050.0]
        exchange_b_prices = [50000.0, 50100.0, 45000.0]

        for price_a, price_b in zip(exchange_a_prices, exchange_b_prices):
            engine.update_price("binance_perp", "BTCUSDT", price_a)
            engine.update_price("bybit_perp", "BTCUSDT", price_b)

            calc = engine.detect_scenario_b_spread(
                price_a, price_b, "binance_perp", "bybit_perp"
            )
            spread = calc.spread

            if price_a < price_b:
                assert calc.premium_exchange == "bybit_perp"
                assert calc.discount_exchange == "binance_perp"
            else:
                assert calc.premium_exchange == "binance_perp"
                assert calc.discount_exchange == "bybit_perp"

    def test_price_cache_update_overwrites(self):
        """Test that price updates overwrite previous values."""
        engine = SpreadDetectionEngine()
        engine.update_price("binance", "BTCUSDT", 45000.0, timestamp=1000)
        assert engine.get_price("binance", "BTCUSDT") == 45000.0

        engine.update_price("binance", "BTCUSDT", 45100.0, timestamp=2000)
        assert engine.get_price("binance", "BTCUSDT") == 45100.0

    def test_price_types(self):
        """Test storing prices with different types."""
        engine = SpreadDetectionEngine()
        engine.update_price(
            "binance", "BTCUSDT", 45000.0, price_type=PriceType.SPOT
        )
        engine.update_price(
            "binance", "BTCUSDT", 45100.0, price_type=PriceType.MARK
        )

        assert engine.get_price("binance", "BTCUSDT") == 45100.0
