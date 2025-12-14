"""Tests for order manager."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from parcer.orders.manager import OrderManager, OrderSide, OrderStatus
from parcer.orders.position import PositionStatus
from parcer.exchanges.protocol import Order


class TestOrderManager:
    """Tests for order management."""

    def test_create_position(self):
        """Test creating a position."""
        manager = OrderManager()
        position = manager.create_position(
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
        assert position.position_id is not None
        assert position.symbol_a == "BTCUSDT"
        assert position.exchange_a == "binance"
        assert position.status == PositionStatus.PENDING

    def test_get_position(self):
        """Test retrieving a position."""
        manager = OrderManager()
        position = manager.create_position(
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
        retrieved = manager.get_position(position.position_id)
        assert retrieved == position

    def test_get_nonexistent_position(self):
        """Test getting a position that doesn't exist."""
        manager = OrderManager()
        assert manager.get_position("nonexistent") is None

    def test_get_active_positions_empty(self):
        """Test getting active positions when none exist."""
        manager = OrderManager()
        assert manager.get_active_positions() == []

    def test_get_active_positions(self):
        """Test getting active positions."""
        manager = OrderManager()
        position = manager.create_position(
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

        active = manager.get_active_positions()
        assert len(active) == 1
        assert active[0] == position

    @pytest.mark.asyncio
    async def test_entry_order_success(self):
        """Test successful entry orders."""
        manager = OrderManager()
        position = manager.create_position(
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

        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        order_a = Order(
            order_id="order_a_123",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=50000.0,
            status="FILLED",
        )
        order_b = Order(
            order_id="order_b_456",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=45000.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(return_value=order_a)
        client_b.place_market_order = AsyncMock(return_value=order_b)

        success = await manager.entry_order(position, client_a, client_b)

        assert success
        assert position.status == PositionStatus.OPENED
        assert position.entry_price_a == 50000.0
        assert position.entry_price_b == 45000.0
        assert position in manager.active_positions

    @pytest.mark.asyncio
    async def test_entry_order_failure(self):
        """Test failed entry orders."""
        manager = OrderManager()
        position = manager.create_position(
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

        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        client_a.place_market_order = AsyncMock(
            side_effect=Exception("Order failed")
        )

        success = await manager.entry_order(position, client_a, client_b)

        assert not success
        assert position.status == PositionStatus.ERROR

    @pytest.mark.asyncio
    async def test_exit_order_success(self):
        """Test successful exit orders."""
        manager = OrderManager()
        position = manager.create_position(
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
        position.leg_a_order_id = "entry_a"
        position.leg_b_order_id = "entry_b"
        manager.active_positions.append(position)

        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        exit_order_a = Order(
            order_id="exit_a_123",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=49000.0,
            status="FILLED",
        )
        exit_order_b = Order(
            order_id="exit_b_456",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=45500.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(return_value=exit_order_a)
        client_b.place_market_order = AsyncMock(return_value=exit_order_b)

        success = await manager.exit_order(position, client_a, client_b)

        assert success
        assert position.status == PositionStatus.CLOSED
        assert position.pnl is not None
        assert position not in manager.active_positions

    @pytest.mark.asyncio
    async def test_exit_order_no_order_ids(self):
        """Test exit order when order IDs are missing."""
        manager = OrderManager()
        position = manager.create_position(
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

        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        success = await manager.exit_order(position, client_a, client_b)

        assert not success

    @pytest.mark.asyncio
    async def test_entry_order_multiple_positions(self):
        """Test entry orders for multiple positions."""
        manager = OrderManager()

        position1 = manager.create_position(
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

        position2 = manager.create_position(
            symbol_a="ETHUSDT",
            exchange_a="binance",
            symbol_b="ETHUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=10.0,
            leg_b_side="sell",
            leg_b_quantity=10.0,
        )

        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        order_a1 = Order(
            order_id="order_a1",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=50000.0,
            status="FILLED",
        )
        order_b1 = Order(
            order_id="order_b1",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=45000.0,
            status="FILLED",
        )
        order_a2 = Order(
            order_id="order_a2",
            symbol="ETHUSDT",
            side="buy",
            quantity=10.0,
            price=3000.0,
            status="FILLED",
        )
        order_b2 = Order(
            order_id="order_b2",
            symbol="ETHUSDT",
            side="sell",
            quantity=10.0,
            price=2900.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(
            side_effect=[order_a1, order_a2]
        )
        client_b.place_market_order = AsyncMock(
            side_effect=[order_b1, order_b2]
        )

        success1 = await manager.entry_order(position1, client_a, client_b)
        success2 = await manager.entry_order(position2, client_a, client_b)

        assert success1
        assert success2
        assert len(manager.active_positions) == 2
