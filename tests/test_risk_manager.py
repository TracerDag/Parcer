"""Tests for risk manager and order rollback behavior."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile

from parcer.orders.manager import OrderManager
from parcer.orders.position import Position, PositionStatus
from parcer.orders.risk_manager import (
    RiskManager,
    InsufficientBalanceError,
    MaxPositionsError,
)
from parcer.exchanges.protocol import Order, Balance
from parcer.settings import Settings, TradingSettings
from parcer.history import TradeHistory


@pytest.fixture
def test_settings():
    """Create test settings."""
    return Settings(
        env="test",
        trading=TradingSettings(
            leverage=3.0,
            max_positions=2,
            fixed_order_size=100.0,
        ),
    )


@pytest.fixture
def risk_manager(test_settings):
    """Create a risk manager instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        history = TradeHistory(Path(tmpdir))
        return RiskManager(test_settings, history)


@pytest.fixture
def order_manager(test_settings):
    """Create an order manager with risk management."""
    with tempfile.TemporaryDirectory() as tmpdir:
        history = TradeHistory(Path(tmpdir))
        return OrderManager(test_settings, history)


class TestRiskManager:
    """Tests for risk manager."""

    @pytest.mark.asyncio
    async def test_check_balance_sufficiency_pass(self, risk_manager):
        """Test balance check passes with sufficient balance."""
        client = AsyncMock()
        balance = Balance("USDT", 1000.0, 0.0)
        client.get_balance = AsyncMock(return_value=balance)

        result = await risk_manager.check_balance_sufficiency(
            client=client,
            exchange_name="binance",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.01,
            price=50000.0,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_check_balance_sufficiency_fail(self, risk_manager):
        """Test balance check fails with insufficient balance."""
        client = AsyncMock()
        balance = Balance("USDT", 10.0, 0.0)
        client.get_balance = AsyncMock(return_value=balance)

        with pytest.raises(InsufficientBalanceError) as exc_info:
            await risk_manager.check_balance_sufficiency(
                client=client,
                exchange_name="binance",
                symbol="BTCUSDT",
                side="buy",
                quantity=1.0,
                price=50000.0,
            )

        assert "Insufficient USDT balance" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_check_balance_with_leverage(self, risk_manager):
        """Test balance check accounts for leverage."""
        client = AsyncMock()
        # With 3x leverage, need 50000/3 = ~16666 USDT for 1 BTC at 50000
        balance = Balance("USDT", 20000.0, 0.0)
        client.get_balance = AsyncMock(return_value=balance)

        result = await risk_manager.check_balance_sufficiency(
            client=client,
            exchange_name="binance",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=50000.0,
        )

        assert result is True

    def test_check_position_limit_pass(self, risk_manager):
        """Test position limit check passes."""
        result = risk_manager.check_position_limit(1)
        assert result is True

    def test_check_position_limit_fail(self, risk_manager):
        """Test position limit check fails at max."""
        with pytest.raises(MaxPositionsError) as exc_info:
            risk_manager.check_position_limit(2)

        assert "Maximum positions limit reached" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_set_leverage_perpetual(self, risk_manager):
        """Test leverage is set for perpetual contracts."""
        client = AsyncMock()
        client.set_leverage = AsyncMock()

        await risk_manager.set_leverage_if_needed(
            client, "binance", "BTCUSDTPERP"
        )

        client.set_leverage.assert_called_once_with(3.0, "BTCUSDTPERP")

    @pytest.mark.asyncio
    async def test_set_leverage_spot(self, risk_manager):
        """Test leverage is not set for spot markets."""
        client = AsyncMock()
        client.set_leverage = AsyncMock()

        await risk_manager.set_leverage_if_needed(
            client, "binance", "BTCUSDT"
        )

        client.set_leverage.assert_not_called()

    def test_get_order_quantity(self, risk_manager):
        """Test order quantity calculation."""
        # fixed_order_size = 100 USDT, price = 50000
        # quantity = 100 / 50000 = 0.002
        quantity = risk_manager.get_order_quantity("BTCUSDT", 50000.0)
        assert quantity == pytest.approx(0.002, rel=1e-6)


class TestOrderRollback:
    """Tests for order rollback behavior."""

    @pytest.mark.asyncio
    async def test_entry_order_rollback_on_second_leg_failure(self, order_manager):
        """Test that first leg is rolled back when second leg fails."""
        position = order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=0.1,
            leg_b_side="sell",
            leg_b_quantity=0.1,
        )

        # Setup mocks
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        # Mock balances - sufficient
        balance = Balance("USDT", 10000.0, 0.0)
        client_a.get_balance = AsyncMock(return_value=balance)
        client_b.get_balance = AsyncMock(return_value=balance)

        # First order succeeds
        order_a = Order(
            order_id="order_a_123",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.1,
            price=50000.0,
            status="FILLED",
        )
        client_a.place_market_order = AsyncMock(return_value=order_a)

        # Second order fails
        client_b.place_market_order = AsyncMock(
            side_effect=Exception("Exchange error")
        )

        # Execute entry order
        success = await order_manager.entry_order(position, client_a, client_b)

        # Should fail
        assert not success
        assert position.status == PositionStatus.ERROR

        # First leg should be placed
        assert client_a.place_market_order.call_count == 2  # Initial + rollback

        # Verify rollback - should place opposite order
        rollback_call = client_a.place_market_order.call_args_list[1]
        assert rollback_call[1]["side"] == "sell"
        assert rollback_call[1]["quantity"] == 0.1

    @pytest.mark.asyncio
    async def test_entry_order_success_both_legs(self, order_manager):
        """Test successful entry order with both legs."""
        position = order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=0.1,
            leg_b_side="sell",
            leg_b_quantity=0.1,
        )

        # Setup mocks
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        # Mock balances
        balance = Balance("USDT", 10000.0, 0.0)
        client_a.get_balance = AsyncMock(return_value=balance)
        client_b.get_balance = AsyncMock(return_value=balance)

        # Both orders succeed
        order_a = Order(
            order_id="order_a_123",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.1,
            price=50000.0,
            status="FILLED",
        )
        order_b = Order(
            order_id="order_b_456",
            symbol="BTCUSDT",
            side="sell",
            quantity=0.1,
            price=50100.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(return_value=order_a)
        client_b.place_market_order = AsyncMock(return_value=order_b)

        # Execute entry order
        success = await order_manager.entry_order(position, client_a, client_b)

        # Should succeed
        assert success
        assert position.status == PositionStatus.OPENED
        assert position in order_manager.active_positions

        # Both legs should be placed exactly once
        assert client_a.place_market_order.call_count == 1
        assert client_b.place_market_order.call_count == 1


class TestBalanceGating:
    """Tests for balance gating."""

    @pytest.mark.asyncio
    async def test_entry_order_insufficient_balance_leg_a(self):
        """Test entry order fails when leg A has insufficient balance."""
        # Create settings with tempdir
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                env="test",
                trading=TradingSettings(
                    leverage=3.0,
                    max_positions=2,
                    fixed_order_size=100.0,
                ),
            )
            history = TradeHistory(Path(tmpdir))
            order_manager = OrderManager(settings, history)
            
            position = order_manager.create_position(
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

            # Setup mocks with price estimate
            client_a = AsyncMock()
            client_b = AsyncMock()
            client_a.name = "binance"
            client_b.name = "bybit"

            # Insufficient balance on client A
            # With 3x leverage, need 50000/3 = ~16667 USDT for 1 BTC at 50000
            balance_a = Balance("USDT", 100.0, 0.0)
            balance_b = Balance("USDT", 50000.0, 0.0)
            client_a.get_balance = AsyncMock(return_value=balance_a)
            client_b.get_balance = AsyncMock(return_value=balance_b)

            # Mock risk manager to use price estimate
            original_check = order_manager.risk_manager.check_balance_sufficiency
            
            async def check_with_price(*args, **kwargs):
                # Add a price estimate if not provided
                if 'price' not in kwargs or kwargs['price'] is None:
                    kwargs['price'] = 50000.0
                return await original_check(*args, **kwargs)
            
            order_manager.risk_manager.check_balance_sufficiency = check_with_price

            # Execute entry order
            success = await order_manager.entry_order(position, client_a, client_b)

            # Should fail
            assert not success
            assert position.status == PositionStatus.ERROR

            # No orders should be placed
            client_a.place_market_order.assert_not_called()
            client_b.place_market_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_entry_order_insufficient_balance_leg_b(self):
        """Test entry order fails when leg B has insufficient balance."""
        # Create settings with tempdir
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                env="test",
                trading=TradingSettings(
                    leverage=3.0,
                    max_positions=2,
                    fixed_order_size=100.0,
                ),
            )
            history = TradeHistory(Path(tmpdir))
            order_manager = OrderManager(settings, history)
            
            position = order_manager.create_position(
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

            # Setup mocks
            client_a = AsyncMock()
            client_b = AsyncMock()
            client_a.name = "binance"
            client_b.name = "bybit"

            # Insufficient balance on client B
            balance_a = Balance("USDT", 50000.0, 0.0)
            balance_b = Balance("USDT", 100.0, 0.0)
            client_a.get_balance = AsyncMock(return_value=balance_a)
            client_b.get_balance = AsyncMock(return_value=balance_b)

            # Mock risk manager to use price estimate
            original_check = order_manager.risk_manager.check_balance_sufficiency
            
            async def check_with_price(*args, **kwargs):
                # Add a price estimate if not provided
                if 'price' not in kwargs or kwargs['price'] is None:
                    kwargs['price'] = 50000.0
                return await original_check(*args, **kwargs)
            
            order_manager.risk_manager.check_balance_sufficiency = check_with_price

            # Execute entry order
            success = await order_manager.entry_order(position, client_a, client_b)

            # Should fail
            assert not success
            assert position.status == PositionStatus.ERROR

            # No orders should be placed
            client_a.place_market_order.assert_not_called()
            client_b.place_market_order.assert_not_called()


class TestMaxPositions:
    """Tests for maximum positions enforcement."""

    @pytest.mark.asyncio
    async def test_entry_order_max_positions_reached(self, order_manager):
        """Test entry order fails when max positions limit is reached."""
        # Create and open two positions (max = 2)
        for i in range(2):
            position = order_manager.create_position(
                symbol_a="BTCUSDT",
                exchange_a="binance",
                symbol_b="BTCUSDT",
                exchange_b="bybit",
                scenario="a",
                leg_a_side="buy",
                leg_a_quantity=0.1,
                leg_b_side="sell",
                leg_b_quantity=0.1,
            )
            position.mark_opened(50000.0, 50100.0)
            order_manager.active_positions.append(position)

        # Try to create third position
        position3 = order_manager.create_position(
            symbol_a="ETHUSDT",
            exchange_a="binance",
            symbol_b="ETHUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )

        # Setup mocks
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        balance = Balance("USDT", 10000.0, 0.0)
        client_a.get_balance = AsyncMock(return_value=balance)
        client_b.get_balance = AsyncMock(return_value=balance)

        # Execute entry order
        success = await order_manager.entry_order(position3, client_a, client_b)

        # Should fail due to max positions
        assert not success
        assert position3.status == PositionStatus.ERROR

        # No orders should be placed
        client_a.place_market_order.assert_not_called()
        client_b.place_market_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_entry_order_within_position_limit(self, order_manager):
        """Test entry order succeeds when within position limit."""
        # Create and open one position
        position1 = order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=0.1,
            leg_b_side="sell",
            leg_b_quantity=0.1,
        )
        position1.mark_opened(50000.0, 50100.0)
        order_manager.active_positions.append(position1)

        # Try to create second position (should succeed, max = 2)
        position2 = order_manager.create_position(
            symbol_a="ETHUSDT",
            exchange_a="binance",
            symbol_b="ETHUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )

        # Setup mocks
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        balance = Balance("USDT", 10000.0, 0.0)
        client_a.get_balance = AsyncMock(return_value=balance)
        client_b.get_balance = AsyncMock(return_value=balance)

        order_a = Order(
            order_id="order_a",
            symbol="ETHUSDT",
            side="buy",
            quantity=1.0,
            price=3000.0,
            status="FILLED",
        )
        order_b = Order(
            order_id="order_b",
            symbol="ETHUSDT",
            side="sell",
            quantity=1.0,
            price=3010.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(return_value=order_a)
        client_b.place_market_order = AsyncMock(return_value=order_b)

        # Execute entry order
        success = await order_manager.entry_order(position2, client_a, client_b)

        # Should succeed
        assert success
        assert position2.status == PositionStatus.OPENED
        assert len(order_manager.active_positions) == 2


class TestLeverageSetting:
    """Tests for leverage setting."""

    @pytest.mark.asyncio
    async def test_leverage_set_for_perpetuals(self, order_manager):
        """Test leverage is set for perpetual contracts."""
        position = order_manager.create_position(
            symbol_a="BTCUSDTPERP",
            exchange_a="binance",
            symbol_b="BTCUSDTPERP",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=0.1,
            leg_b_side="sell",
            leg_b_quantity=0.1,
        )

        # Setup mocks
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        balance = Balance("USDT", 10000.0, 0.0)
        client_a.get_balance = AsyncMock(return_value=balance)
        client_b.get_balance = AsyncMock(return_value=balance)
        client_a.set_leverage = AsyncMock()
        client_b.set_leverage = AsyncMock()

        order_a = Order(
            order_id="order_a",
            symbol="BTCUSDTPERP",
            side="buy",
            quantity=0.1,
            price=50000.0,
            status="FILLED",
        )
        order_b = Order(
            order_id="order_b",
            symbol="BTCUSDTPERP",
            side="sell",
            quantity=0.1,
            price=50100.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(return_value=order_a)
        client_b.place_market_order = AsyncMock(return_value=order_b)

        # Execute entry order
        success = await order_manager.entry_order(position, client_a, client_b)

        # Should succeed
        assert success

        # Leverage should be set on both clients
        client_a.set_leverage.assert_called_once_with(3.0, "BTCUSDTPERP")
        client_b.set_leverage.assert_called_once_with(3.0, "BTCUSDTPERP")

    @pytest.mark.asyncio
    async def test_leverage_not_set_for_spot(self, order_manager):
        """Test leverage is not set for spot markets."""
        position = order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance",
            symbol_b="BTCUSDT",
            exchange_b="bybit",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=0.1,
            leg_b_side="sell",
            leg_b_quantity=0.1,
        )

        # Setup mocks
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance"
        client_b.name = "bybit"

        balance = Balance("USDT", 10000.0, 0.0)
        client_a.get_balance = AsyncMock(return_value=balance)
        client_b.get_balance = AsyncMock(return_value=balance)
        client_a.set_leverage = AsyncMock()
        client_b.set_leverage = AsyncMock()

        order_a = Order(
            order_id="order_a",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.1,
            price=50000.0,
            status="FILLED",
        )
        order_b = Order(
            order_id="order_b",
            symbol="BTCUSDT",
            side="sell",
            quantity=0.1,
            price=50100.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(return_value=order_a)
        client_b.place_market_order = AsyncMock(return_value=order_b)

        # Execute entry order
        success = await order_manager.entry_order(position, client_a, client_b)

        # Should succeed
        assert success

        # Leverage should not be set for spot markets
        client_a.set_leverage.assert_not_called()
        client_b.set_leverage.assert_not_called()
