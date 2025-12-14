"""Tests for arbitrage scenario strategies."""

import pytest
from unittest.mock import AsyncMock, patch

from parcer.strategy.spread_engine import SpreadDetectionEngine, PriceType
from parcer.strategy.scenario_a import ScenarioAStrategy
from parcer.strategy.scenario_b import ScenarioBStrategy
from parcer.orders.manager import OrderManager
from parcer.orders.position import PositionStatus
from parcer.exchanges.protocol import Order


class TestScenarioAStrategy:
    """Tests for Scenario A (spot vs futures) strategy."""

    def setup_method(self):
        """Setup test fixtures."""
        self.spread_engine = SpreadDetectionEngine()
        self.order_manager = OrderManager()
        self.strategy = ScenarioAStrategy(
            self.spread_engine, self.order_manager
        )

    def test_initial_state(self):
        """Test strategy initial state."""
        assert self.strategy.current_position is None

    @pytest.mark.asyncio
    async def test_entry_no_position(self):
        """Test entry with no open position."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_futures"
        client_b.name = "binance_spot"

        order_a = Order(
            order_id="order_a",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=50000.0,
            status="FILLED",
        )
        order_b = Order(
            order_id="order_b",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=45000.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(return_value=order_a)
        client_b.place_market_order = AsyncMock(return_value=order_b)

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 50000.0, price_type=PriceType.MARK
        )
        self.spread_engine.update_price(
            client_b.name, "BTCUSDT", 45000.0, price_type=PriceType.SPOT
        )

        with patch(
            "parcer.strategy.scenario_a.check_symbol_mismatch"
        ) as mock_check:
            position = await self.strategy.check_entry(
                client_a,
                client_b,
                "BTCUSDT",
                "BTCUSDT",
                entry_threshold=0.05,
                entry_quantity=1.0,
            )

        assert position is not None
        assert position.status == PositionStatus.OPENED
        assert self.strategy.current_position == position

    @pytest.mark.asyncio
    async def test_entry_threshold_not_met(self):
        """Test entry when threshold is not met."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_futures"
        client_b.name = "binance_spot"

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 50000.0, price_type=PriceType.MARK
        )
        self.spread_engine.update_price(
            client_b.name, "BTCUSDT", 49500.0, price_type=PriceType.SPOT
        )

        position = await self.strategy.check_entry(
            client_a,
            client_b,
            "BTCUSDT",
            "BTCUSDT",
            entry_threshold=0.02,
            entry_quantity=1.0,
        )

        assert position is None
        assert self.strategy.current_position is None

    @pytest.mark.asyncio
    async def test_entry_missing_prices(self):
        """Test entry when prices are missing."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_futures"
        client_b.name = "binance_spot"

        position = await self.strategy.check_entry(
            client_a,
            client_b,
            "BTCUSDT",
            "BTCUSDT",
            entry_threshold=0.05,
            entry_quantity=1.0,
        )

        assert position is None

    @pytest.mark.asyncio
    async def test_entry_already_open_position(self):
        """Test entry when position already open."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_futures"
        client_b.name = "binance_spot"

        position1 = self.order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance_futures",
            symbol_b="BTCUSDT",
            exchange_b="binance_spot",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position1.mark_opened(50000.0, 45000.0)
        self.strategy.current_position = position1

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 50000.0, price_type=PriceType.MARK
        )
        self.spread_engine.update_price(
            client_b.name, "BTCUSDT", 45000.0, price_type=PriceType.SPOT
        )

        position2 = await self.strategy.check_entry(
            client_a,
            client_b,
            "BTCUSDT",
            "BTCUSDT",
            entry_threshold=0.05,
            entry_quantity=1.0,
        )

        assert position2 is None
        assert self.strategy.current_position == position1

    @pytest.mark.asyncio
    async def test_exit_success(self):
        """Test successful exit."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_futures"
        client_b.name = "binance_spot"

        position = self.order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance_futures",
            symbol_b="BTCUSDT",
            exchange_b="binance_spot",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.leg_a_order_id = "order_a"
        position.leg_b_order_id = "order_b"
        position.mark_opened(50000.0, 45000.0)
        self.strategy.current_position = position
        self.order_manager.active_positions.append(position)

        exit_order_a = Order(
            order_id="exit_a",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=45500.0,
            status="FILLED",
        )
        exit_order_b = Order(
            order_id="exit_b",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=45400.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(return_value=exit_order_a)
        client_b.place_market_order = AsyncMock(return_value=exit_order_b)

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 45500.0, price_type=PriceType.MARK
        )
        self.spread_engine.update_price(
            client_b.name, "BTCUSDT", 45400.0, price_type=PriceType.SPOT
        )

        success = await self.strategy.check_exit(
            client_a, client_b, exit_threshold=0.005
        )

        assert success
        assert position.status == PositionStatus.CLOSED
        assert self.strategy.current_position is None

    @pytest.mark.asyncio
    async def test_exit_no_open_position(self):
        """Test exit with no open position."""
        client_a = AsyncMock()
        client_b = AsyncMock()

        success = await self.strategy.check_exit(client_a, client_b, 0.01)

        assert not success

    @pytest.mark.asyncio
    async def test_exit_threshold_not_met(self):
        """Test exit when threshold not met."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_futures"
        client_b.name = "binance_spot"

        position = self.order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance_futures",
            symbol_b="BTCUSDT",
            exchange_b="binance_spot",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.mark_opened(50000.0, 45000.0)
        self.strategy.current_position = position

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 49000.0, price_type=PriceType.MARK
        )
        self.spread_engine.update_price(
            client_b.name, "BTCUSDT", 45000.0, price_type=PriceType.SPOT
        )

        success = await self.strategy.check_exit(
            client_a, client_b, exit_threshold=0.02
        )

        assert not success
        assert self.strategy.current_position == position

    def test_get_current_position(self):
        """Test getting current position."""
        assert self.strategy.get_current_position() is None

        position = self.order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance_futures",
            symbol_b="BTCUSDT",
            exchange_b="binance_spot",
            scenario="a",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        self.strategy.current_position = position

        assert self.strategy.get_current_position() == position


class TestScenarioBStrategy:
    """Tests for Scenario B (futures vs futures) strategy."""

    def setup_method(self):
        """Setup test fixtures."""
        self.spread_engine = SpreadDetectionEngine()
        self.order_manager = OrderManager()
        self.strategy = ScenarioBStrategy(
            self.spread_engine, self.order_manager
        )

    def test_initial_state(self):
        """Test strategy initial state."""
        assert self.strategy.current_position is None

    @pytest.mark.asyncio
    async def test_entry_spread_exceeds_threshold(self):
        """Test entry when spread exceeds 7% threshold."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_perp"
        client_b.name = "bybit_perp"

        order_a = Order(
            order_id="order_a",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=45000.0,
            status="FILLED",
        )
        order_b = Order(
            order_id="order_b",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=50000.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(return_value=order_a)
        client_b.place_market_order = AsyncMock(return_value=order_b)

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 45000.0, price_type=PriceType.MARK
        )
        self.spread_engine.update_price(
            client_b.name, "BTCUSDT", 50000.0, price_type=PriceType.MARK
        )

        with patch(
            "parcer.strategy.scenario_b.check_symbol_mismatch"
        ) as mock_check:
            position = await self.strategy.check_entry(
                client_a,
                client_b,
                "BTCUSDT",
                "BTCUSDT",
                entry_threshold=0.07,
                entry_quantity=1.0,
            )

        assert position is not None
        assert position.status == PositionStatus.OPENED

    @pytest.mark.asyncio
    async def test_entry_threshold_not_met(self):
        """Test entry when threshold not met."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_perp"
        client_b.name = "bybit_perp"

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 49000.0, price_type=PriceType.MARK
        )
        self.spread_engine.update_price(
            client_b.name, "BTCUSDT", 50000.0, price_type=PriceType.MARK
        )

        position = await self.strategy.check_entry(
            client_a,
            client_b,
            "BTCUSDT",
            "BTCUSDT",
            entry_threshold=0.07,
            entry_quantity=1.0,
        )

        assert position is None

    @pytest.mark.asyncio
    async def test_entry_missing_prices(self):
        """Test entry when prices are missing."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_perp"
        client_b.name = "bybit_perp"

        position = await self.strategy.check_entry(
            client_a,
            client_b,
            "BTCUSDT",
            "BTCUSDT",
            entry_threshold=0.07,
            entry_quantity=1.0,
        )

        assert position is None

    @pytest.mark.asyncio
    async def test_exit_spread_below_1_percent(self):
        """Test exit when spread drops below 1%."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_perp"
        client_b.name = "bybit_perp"

        position = self.order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance_perp",
            symbol_b="BTCUSDT",
            exchange_b="bybit_perp",
            scenario="b",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.leg_a_order_id = "order_a"
        position.leg_b_order_id = "order_b"
        position.mark_opened(45000.0, 50000.0)
        self.strategy.current_position = position

        exit_order_a = Order(
            order_id="exit_a",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=49500.0,
            status="FILLED",
        )
        exit_order_b = Order(
            order_id="exit_b",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=49750.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(return_value=exit_order_a)
        client_b.place_market_order = AsyncMock(return_value=exit_order_b)

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 49500.0, price_type=PriceType.MARK
        )
        self.spread_engine.update_price(
            client_b.name, "BTCUSDT", 49750.0, price_type=PriceType.MARK
        )

        success = await self.strategy.check_exit(
            client_a, client_b, "BTCUSDT", "BTCUSDT", exit_threshold=0.01
        )

        assert success
        assert position.status == PositionStatus.CLOSED

    @pytest.mark.asyncio
    async def test_exit_threshold_not_met(self):
        """Test exit when threshold not met."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_perp"
        client_b.name = "bybit_perp"

        position = self.order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance_perp",
            symbol_b="BTCUSDT",
            exchange_b="bybit_perp",
            scenario="b",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        position.mark_opened(45000.0, 50000.0)
        self.strategy.current_position = position

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 46000.0, price_type=PriceType.MARK
        )
        self.spread_engine.update_price(
            client_b.name, "BTCUSDT", 50000.0, price_type=PriceType.MARK
        )

        success = await self.strategy.check_exit(
            client_a, client_b, "BTCUSDT", "BTCUSDT", exit_threshold=0.01
        )

        assert not success
        assert self.strategy.current_position == position

    def test_get_current_position(self):
        """Test getting current position."""
        assert self.strategy.get_current_position() is None

        position = self.order_manager.create_position(
            symbol_a="BTCUSDT",
            exchange_a="binance_perp",
            symbol_b="BTCUSDT",
            exchange_b="bybit_perp",
            scenario="b",
            leg_a_side="buy",
            leg_a_quantity=1.0,
            leg_b_side="sell",
            leg_b_quantity=1.0,
        )
        self.strategy.current_position = position

        assert self.strategy.get_current_position() == position


class TestDuplicateTokenValidation:
    """Tests for duplicate token validation."""

    @pytest.mark.asyncio
    async def test_scenario_a_symbol_check(self):
        """Test symbol mismatch check in Scenario A."""
        spread_engine = SpreadDetectionEngine()
        order_manager = OrderManager()
        strategy = ScenarioAStrategy(spread_engine, order_manager)

        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_futures"
        client_b.name = "binance_spot"

        spread_engine.update_price(
            client_a.name, "BTCUSDT", 50000.0, price_type=PriceType.MARK
        )
        spread_engine.update_price(
            client_b.name, "BTCUSDT", 45000.0, price_type=PriceType.SPOT
        )

        with patch(
            "parcer.strategy.scenario_a.check_symbol_mismatch"
        ) as mock_check:
            order_a = Order(
                order_id="order_a",
                symbol="BTCUSDT",
                side="buy",
                quantity=1.0,
                price=50000.0,
                status="FILLED",
            )
            order_b = Order(
                order_id="order_b",
                symbol="BTCUSDT",
                side="sell",
                quantity=1.0,
                price=45000.0,
                status="FILLED",
            )

            client_a.place_market_order = AsyncMock(return_value=order_a)
            client_b.place_market_order = AsyncMock(return_value=order_b)

            await strategy.check_entry(
                client_a,
                client_b,
                "BTCUSDT",
                "BTCUSDT",
                entry_threshold=0.05,
                entry_quantity=1.0,
            )

            mock_check.assert_called_once_with("BTCUSDT", "BTCUSDT")

    @pytest.mark.asyncio
    async def test_scenario_b_symbol_check(self):
        """Test symbol mismatch check in Scenario B."""
        spread_engine = SpreadDetectionEngine()
        order_manager = OrderManager()
        strategy = ScenarioBStrategy(spread_engine, order_manager)

        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_perp"
        client_b.name = "bybit_perp"

        spread_engine.update_price(
            client_a.name, "BTCUSDT", 45000.0, price_type=PriceType.MARK
        )
        spread_engine.update_price(
            client_b.name, "BTCUSDT", 50000.0, price_type=PriceType.MARK
        )

        with patch(
            "parcer.strategy.scenario_b.check_symbol_mismatch"
        ) as mock_check:
            order_a = Order(
                order_id="order_a",
                symbol="BTCUSDT",
                side="buy",
                quantity=1.0,
                price=45000.0,
                status="FILLED",
            )
            order_b = Order(
                order_id="order_b",
                symbol="BTCUSDT",
                side="sell",
                quantity=1.0,
                price=50000.0,
                status="FILLED",
            )

            client_a.place_market_order = AsyncMock(return_value=order_a)
            client_b.place_market_order = AsyncMock(return_value=order_b)

            await strategy.check_entry(
                client_a,
                client_b,
                "BTCUSDT",
                "BTCUSDT",
                entry_threshold=0.07,
                entry_quantity=1.0,
            )

            mock_check.assert_called_once_with("BTCUSDT", "BTCUSDT")
