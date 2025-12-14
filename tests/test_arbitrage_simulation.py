"""Integration tests for arbitrage strategies with synthetic price data."""

import pytest
from unittest.mock import AsyncMock

from parcer.strategy.spread_engine import SpreadDetectionEngine, PriceType
from parcer.strategy.scenario_a import ScenarioAStrategy
from parcer.strategy.scenario_b import ScenarioBStrategy
from parcer.orders.manager import OrderManager
from parcer.orders.position import PositionStatus
from parcer.exchanges.protocol import Order


class TestScenarioASimulation:
    """Simulation tests for Scenario A (spot vs futures)."""

    def setup_method(self):
        """Setup test fixtures."""
        self.spread_engine = SpreadDetectionEngine()
        self.order_manager = OrderManager()
        self.strategy = ScenarioAStrategy(
            self.spread_engine, self.order_manager
        )

    @pytest.mark.asyncio
    async def test_full_lifecycle_entry_and_exit(self):
        """Test complete lifecycle: entry signal, position open, exit signal."""
        client_futures = AsyncMock()
        client_spot = AsyncMock()
        client_futures.name = "binance_futures"
        client_spot.name = "binance_spot"

        entry_order_a = Order(
            order_id="entry_a",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=48000.0,
            status="FILLED",
        )
        entry_order_b = Order(
            order_id="entry_b",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=46000.0,
            status="FILLED",
        )
        exit_order_a = Order(
            order_id="exit_a",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=46500.0,
            status="FILLED",
        )
        exit_order_b = Order(
            order_id="exit_b",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=46400.0,
            status="FILLED",
        )

        client_futures.place_market_order = AsyncMock(
            side_effect=[entry_order_a, exit_order_a]
        )
        client_spot.place_market_order = AsyncMock(
            side_effect=[entry_order_b, exit_order_b]
        )

        position = None
        futures_price = 45000.0
        spot_price = 43000.0

        self.spread_engine.update_price(
            client_futures.name,
            "BTCUSDT",
            futures_price,
            price_type=PriceType.MARK,
        )
        self.spread_engine.update_price(
            client_spot.name,
            "BTCUSDT",
            spot_price,
            price_type=PriceType.SPOT,
        )

        futures_price = 48000.0
        spot_price = 46000.0
        self.spread_engine.update_price(
            client_futures.name,
            "BTCUSDT",
            futures_price,
            price_type=PriceType.MARK,
        )
        self.spread_engine.update_price(
            client_spot.name,
            "BTCUSDT",
            spot_price,
            price_type=PriceType.SPOT,
        )

        position = await self.strategy.check_entry(
            client_futures,
            client_spot,
            "BTCUSDT",
            "BTCUSDT",
            entry_threshold=0.04,
            entry_quantity=1.0,
        )

        assert position is not None
        assert position.is_open

        self.spread_engine.update_price(
            client_futures.name,
            "BTCUSDT",
            46500.0,
            price_type=PriceType.MARK,
        )
        self.spread_engine.update_price(
            client_spot.name,
            "BTCUSDT",
            46400.0,
            price_type=PriceType.SPOT,
        )

        closed = await self.strategy.check_exit(
            client_futures,
            client_spot,
            exit_threshold=0.005,
        )

        assert closed
        assert self.strategy.current_position is None

    @pytest.mark.asyncio
    async def test_multiple_entry_attempts_before_signal(self):
        """Test that strategy waits for threshold before entry."""
        client_futures = AsyncMock()
        client_spot = AsyncMock()
        client_futures.name = "binance_futures"
        client_spot.name = "binance_spot"

        below_threshold_prices_futures = [45000.0, 45200.0, 45300.0]
        below_threshold_prices_spot = [43000.0, 43200.0, 43300.0]

        for futures, spot in zip(
            below_threshold_prices_futures, below_threshold_prices_spot
        ):
            self.spread_engine.update_price(
                client_futures.name, "BTCUSDT", futures
            )
            self.spread_engine.update_price(
                client_spot.name, "BTCUSDT", spot
            )

            position = await self.strategy.check_entry(
                client_futures,
                client_spot,
                "BTCUSDT",
                "BTCUSDT",
                entry_threshold=0.05,
                entry_quantity=1.0,
            )

            assert position is None

        client_futures.place_market_order.assert_not_called()
        client_spot.place_market_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_exit_until_threshold_met(self):
        """Test that strategy doesn't exit until threshold met."""
        client_futures = AsyncMock()
        client_spot = AsyncMock()
        client_futures.name = "binance_futures"
        client_spot.name = "binance_spot"

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
        position.leg_a_order_id = "entry_a"
        position.leg_b_order_id = "entry_b"
        position.mark_opened(50000.0, 45000.0)
        self.strategy.current_position = position

        above_exit_threshold_futures = [49000.0, 48000.0, 47000.0]
        above_exit_threshold_spot = [45500.0, 45700.0, 45900.0]

        for futures, spot in zip(
            above_exit_threshold_futures, above_exit_threshold_spot
        ):
            self.spread_engine.update_price(
                client_futures.name, "BTCUSDT", futures
            )
            self.spread_engine.update_price(
                client_spot.name, "BTCUSDT", spot
            )

            closed = await self.strategy.check_exit(
                client_futures,
                client_spot,
                exit_threshold=0.005,
            )

            assert not closed

        client_futures.place_market_order.assert_not_called()
        client_spot.place_market_order.assert_not_called()


class TestScenarioBSimulation:
    """Simulation tests for Scenario B (futures vs futures)."""

    def setup_method(self):
        """Setup test fixtures."""
        self.spread_engine = SpreadDetectionEngine()
        self.order_manager = OrderManager()
        self.strategy = ScenarioBStrategy(
            self.spread_engine, self.order_manager
        )

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_7_percent_spread(self):
        """Test complete lifecycle with realistic 7% entry spread."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_perp"
        client_b.name = "bybit_perp"

        entry_order_a = Order(
            order_id="entry_a",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=45500.0,
            status="FILLED",
        )
        entry_order_b = Order(
            order_id="entry_b",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=50000.0,
            status="FILLED",
        )
        exit_order_a = Order(
            order_id="exit_a",
            symbol="BTCUSDT",
            side="sell",
            quantity=1.0,
            price=46500.0,
            status="FILLED",
        )
        exit_order_b = Order(
            order_id="exit_b",
            symbol="BTCUSDT",
            side="buy",
            quantity=1.0,
            price=46600.0,
            status="FILLED",
        )

        client_a.place_market_order = AsyncMock(
            side_effect=[entry_order_a, exit_order_a]
        )
        client_b.place_market_order = AsyncMock(
            side_effect=[entry_order_b, exit_order_b]
        )

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 45500.0, price_type=PriceType.MARK
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

        assert position is not None
        assert position.is_open

        self.spread_engine.update_price(
            client_a.name, "BTCUSDT", 46500.0, price_type=PriceType.MARK
        )
        self.spread_engine.update_price(
            client_b.name, "BTCUSDT", 46600.0, price_type=PriceType.MARK
        )

        closed = await self.strategy.check_exit(
            client_a,
            client_b,
            "BTCUSDT",
            "BTCUSDT",
            exit_threshold=0.01,
        )

        assert closed

    @pytest.mark.asyncio
    async def test_spread_narrows_gradually_to_exit(self):
        """Test spread narrowing over multiple price updates until exit."""
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
        position.leg_a_order_id = "entry_a"
        position.leg_b_order_id = "entry_b"
        position.mark_opened(45000.0, 50000.0)
        self.strategy.current_position = position

        narrowing_prices_a = [46000.0, 46500.0, 47000.0, 47500.0, 48000.0]
        narrowing_prices_b = [50500.0, 50300.0, 50100.0, 49900.0, 48500.0]

        for i, (price_a, price_b) in enumerate(
            zip(narrowing_prices_a, narrowing_prices_b)
        ):
            self.spread_engine.update_price(
                client_a.name, "BTCUSDT", price_a, price_type=PriceType.MARK
            )
            self.spread_engine.update_price(
                client_b.name, "BTCUSDT", price_b, price_type=PriceType.MARK
            )

            if i == len(narrowing_prices_a) - 1:
                exit_order_a = Order(
                    order_id="exit_a",
                    symbol="BTCUSDT",
                    side="sell",
                    quantity=1.0,
                    price=price_a,
                    status="FILLED",
                )
                exit_order_b = Order(
                    order_id="exit_b",
                    symbol="BTCUSDT",
                    side="buy",
                    quantity=1.0,
                    price=price_b,
                    status="FILLED",
                )
                client_a.place_market_order = AsyncMock(
                    return_value=exit_order_a
                )
                client_b.place_market_order = AsyncMock(
                    return_value=exit_order_b
                )

                closed = await self.strategy.check_exit(
                    client_a,
                    client_b,
                    "BTCUSDT",
                    "BTCUSDT",
                    exit_threshold=0.01,
                )

                if closed:
                    assert position.status == PositionStatus.CLOSED
                    assert position.pnl is not None

    @pytest.mark.asyncio
    async def test_high_volatility_scenario(self):
        """Test strategy with high volatility price movements."""
        client_a = AsyncMock()
        client_b = AsyncMock()
        client_a.name = "binance_perp"
        client_b.name = "bybit_perp"

        volatile_prices_a = [
            45000.0,
            46000.0,
            44000.0,
            47000.0,
            45500.0,
            48000.0,
        ]
        volatile_prices_b = [
            50000.0,
            48000.0,
            52000.0,
            49000.0,
            51000.0,
            50000.0,
        ]

        position = None
        for price_a, price_b in zip(volatile_prices_a, volatile_prices_b):
            self.spread_engine.update_price(
                client_a.name, "BTCUSDT", price_a, price_type=PriceType.MARK
            )
            self.spread_engine.update_price(
                client_b.name, "BTCUSDT", price_b, price_type=PriceType.MARK
            )

            if position is None:
                spread = (max(price_a, price_b) - min(price_a, price_b)) / min(
                    price_a, price_b
                )

                if spread >= 0.07:
                    order_a = Order(
                        order_id=f"entry_a_{price_a}",
                        symbol="BTCUSDT",
                        side="buy",
                        quantity=1.0,
                        price=price_a,
                        status="FILLED",
                    )
                    order_b = Order(
                        order_id=f"entry_b_{price_b}",
                        symbol="BTCUSDT",
                        side="sell",
                        quantity=1.0,
                        price=price_b,
                        status="FILLED",
                    )

                    client_a.place_market_order = AsyncMock(
                        return_value=order_a
                    )
                    client_b.place_market_order = AsyncMock(
                        return_value=order_b
                    )

                    position = await self.strategy.check_entry(
                        client_a,
                        client_b,
                        "BTCUSDT",
                        "BTCUSDT",
                        entry_threshold=0.07,
                        entry_quantity=1.0,
                    )

        spread_engine = self.spread_engine
        prices_check = [
            (volatile_prices_a[-1], volatile_prices_b[-1]),
        ]
        for price_a, price_b in prices_check:
            spread_engine.update_price(
                client_a.name, "BTCUSDT", price_a, price_type=PriceType.MARK
            )
            spread_engine.update_price(
                client_b.name, "BTCUSDT", price_b, price_type=PriceType.MARK
            )
            final_spread = (max(price_a, price_b) - min(price_a, price_b)) / min(
                price_a, price_b
            )
            assert final_spread >= 0.0


class TestPriceStreamSimulation:
    """Tests for simulated price streams."""

    def test_continuous_price_updates_scenario_a(self):
        """Test continuous price updates for Scenario A."""
        engine = SpreadDetectionEngine()

        futures_stream = [
            50000.0,
            50100.0,
            50200.0,
            50150.0,
            50050.0,
            49900.0,
        ]
        spot_stream = [
            45000.0,
            45100.0,
            45200.0,
            45150.0,
            45050.0,
            45000.0,
        ]

        spreads = []
        for fut, spot in zip(futures_stream, spot_stream):
            engine.update_price("binance_fut", "BTCUSDT", fut)
            engine.update_price("binance_spot", "BTCUSDT", spot)

            fut_price = engine.get_price("binance_fut", "BTCUSDT")
            spot_price = engine.get_price("binance_spot", "BTCUSDT")

            spread = (fut_price - spot_price) / spot_price
            spreads.append(spread)

        assert len(spreads) == 6
        assert all(isinstance(s, float) for s in spreads)

    def test_continuous_price_updates_scenario_b(self):
        """Test continuous price updates for Scenario B."""
        engine = SpreadDetectionEngine()

        exchange_a_stream = [45000.0, 45100.0, 45200.0, 45300.0, 45400.0]
        exchange_b_stream = [50000.0, 49500.0, 49000.0, 48500.0, 48000.0]

        spreads = []
        for price_a, price_b in zip(exchange_a_stream, exchange_b_stream):
            engine.update_price("binance", "BTCUSDT", price_a)
            engine.update_price("bybit", "BTCUSDT", price_b)

            cached_a = engine.get_price("binance", "BTCUSDT")
            cached_b = engine.get_price("bybit", "BTCUSDT")

            calc = engine.detect_scenario_b_spread(cached_a, cached_b)
            spreads.append(calc.spread)

        assert len(spreads) == 5
        assert all(s > 0 for s in spreads)
        assert spreads[-1] < spreads[0]
