"""Tests for position tracking."""

import pytest
from datetime import datetime

from parcer.orders.position import Position, PositionStatus


class TestPosition:
    """Tests for position lifecycle."""

    def test_create_position(self):
        """Test position creation."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        assert position.position_id == "pos_123"
        assert position.status == PositionStatus.PENDING
        assert position.created_at is not None

    def test_position_pending_status(self):
        """Test position is pending on creation."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        assert not position.is_open
        assert not position.is_closed

    def test_mark_opened(self):
        """Test marking position as opened."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.mark_opened(50000.0, 45000.0)
        assert position.status == PositionStatus.OPENED
        assert position.is_open
        assert position.opened_at is not None
        assert position.entry_price_a == 50000.0
        assert position.entry_price_b == 45000.0

    def test_calculate_spread_scenario_a_on_open(self):
        """Test spread calculation on open for scenario A."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.mark_opened(50000.0, 45000.0)
        expected_spread = (50000.0 - 45000.0) / 45000.0
        assert position.entry_spread == pytest.approx(expected_spread)

    def test_calculate_spread_scenario_b_on_open(self):
        """Test spread calculation on open for scenario B."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="b",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.mark_opened(45000.0, 50000.0)
        expected_spread = (50000.0 - 45000.0) / 45000.0
        assert position.entry_spread == pytest.approx(expected_spread)

    def test_mark_closed(self):
        """Test marking position as closed."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.mark_opened(50000.0, 45000.0)
        position.mark_closed(49000.0, 45500.0)
        assert position.status == PositionStatus.CLOSED
        assert position.is_closed
        assert position.closed_at is not None

    def test_calculate_pnl_scenario_a(self):
        """Test PnL calculation for scenario A."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.mark_opened(50000.0, 45000.0)
        position.mark_closed(49000.0, 45500.0)

        leg_a_pnl = (50000.0 - 49000.0) * 1.0
        leg_b_pnl = (45500.0 - 45000.0) * 1.0
        expected_pnl = leg_a_pnl + leg_b_pnl

        assert position.pnl == pytest.approx(expected_pnl)

    def test_calculate_pnl_scenario_b(self):
        """Test PnL calculation for scenario B."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="b",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.mark_opened(45000.0, 50000.0)
        position.mark_closed(46000.0, 49000.0)

        leg_a_pnl = (46000.0 - 45000.0) * 1.0
        leg_b_pnl = (50000.0 - 49000.0) * 1.0
        expected_pnl = leg_a_pnl + leg_b_pnl

        assert position.pnl == pytest.approx(expected_pnl)

    def test_mark_error(self):
        """Test marking position with error."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.mark_error()
        assert position.status == PositionStatus.ERROR

    def test_position_lifecycle(self):
        """Test complete position lifecycle."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )

        assert position.status == PositionStatus.PENDING
        assert not position.is_open

        position.mark_opened(50000.0, 45000.0)
        assert position.status == PositionStatus.OPENED
        assert position.is_open
        assert position.opened_at is not None

        position.mark_closed(49000.0, 45500.0)
        assert position.status == PositionStatus.CLOSED
        assert position.is_closed
        assert position.closed_at is not None
        assert position.pnl is not None

    def test_position_with_large_quantities(self):
        """Test position with large quantities."""
        position = Position(
            position_id="pos_123",
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=100.0,
            leg_b_side="sell",
            leg_b_quantity=100.0,
        )
        position.mark_opened(50000.0, 45000.0)
        position.mark_closed(49000.0, 45500.0)

        leg_a_pnl = (50000.0 - 49000.0) * 100.0
        leg_b_pnl = (45500.0 - 45000.0) * 100.0
        expected_pnl = leg_a_pnl + leg_b_pnl

        assert position.pnl == pytest.approx(expected_pnl)
