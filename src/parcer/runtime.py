from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .di import AppContainer
from .history import TradeHistory
from .orders.manager import OrderManager
from .strategy.scenario_a import ScenarioAStrategy
from .strategy.scenario_b import ScenarioBStrategy
from .strategy.spread_engine import PriceType, SpreadDetectionEngine

logger = logging.getLogger(__name__)


async def run(container: AppContainer) -> None:
    logger.info("runtime starting")
    logger.debug("settings=%s", container.settings.redacted())

    arb = container.settings.arbitrage
    if not arb.enabled:
        await asyncio.sleep(0)
        logger.info("runtime stopped")
        return

    if not arb.exchange_a or not arb.exchange_b or not arb.symbol:
        logger.error(
            "arbitrage is enabled but is missing exchange_a/exchange_b/symbol configuration"
        )
        await asyncio.sleep(0)
        logger.info("runtime stopped")
        return

    if arb.exchange_a not in container.exchange_clients:
        logger.error("exchange client not initialized: %s", arb.exchange_a)
        await asyncio.sleep(0)
        logger.info("runtime stopped")
        return

    if arb.exchange_b not in container.exchange_clients:
        logger.error("exchange client not initialized: %s", arb.exchange_b)
        await asyncio.sleep(0)
        logger.info("runtime stopped")
        return

    history = TradeHistory(Path("data"))
    order_manager = OrderManager(container.settings, history)
    spread_engine = SpreadDetectionEngine()

    client_a = container.exchange_clients[arb.exchange_a]
    client_b = container.exchange_clients[arb.exchange_b]

    async def _consume_mark_price(exchange_client, symbol: str) -> None:
        async for update in exchange_client.stream_mark_price(symbol):
            spread_engine.update_price(
                exchange=exchange_client.name,
                symbol=symbol,
                price=update.price,
                price_type=PriceType.MARK,
                timestamp=update.timestamp,
            )
            if container.shutdown.is_set():
                return

    async def _consume_spot_price(exchange_client, symbol: str) -> None:
        async for update in exchange_client.stream_spot_price(symbol):
            spread_engine.update_price(
                exchange=exchange_client.name,
                symbol=symbol,
                price=update.price,
                price_type=PriceType.SPOT,
                timestamp=update.timestamp,
            )
            if container.shutdown.is_set():
                return

    async def _trade_loop_scenario_a() -> None:
        strategy = ScenarioAStrategy(spread_engine, order_manager)

        while not container.shutdown.is_set():
            futures_price = spread_engine.get_price(client_a.name, arb.symbol)
            spot_price = spread_engine.get_price(client_b.name, arb.symbol)

            price_for_qty = spot_price or futures_price
            quantity = (
                order_manager.risk_manager.get_order_quantity(arb.symbol, price_for_qty)
                if order_manager.risk_manager and price_for_qty
                else 0.001
            )

            if strategy.current_position is None:
                await strategy.check_entry(
                    futures_client=client_a,
                    spot_client=client_b,
                    futures_symbol=arb.symbol,
                    spot_symbol=arb.symbol,
                    entry_threshold=arb.entry_threshold,
                    entry_quantity=quantity,
                )
            else:
                await strategy.check_exit(
                    futures_client=client_a,
                    spot_client=client_b,
                    exit_threshold=arb.exit_threshold,
                )

            await asyncio.sleep(0.5)

    async def _trade_loop_scenario_b() -> None:
        strategy = ScenarioBStrategy(spread_engine, order_manager)

        while not container.shutdown.is_set():
            price_a = spread_engine.get_price(client_a.name, arb.symbol)
            price_b = spread_engine.get_price(client_b.name, arb.symbol)

            price_for_qty = min(
                p for p in (price_a, price_b) if p is not None
            ) if (price_a is not None or price_b is not None) else None

            quantity = (
                order_manager.risk_manager.get_order_quantity(arb.symbol, price_for_qty)
                if order_manager.risk_manager and price_for_qty
                else 0.001
            )

            if strategy.current_position is None:
                await strategy.check_entry(
                    exchange_a_client=client_a,
                    exchange_b_client=client_b,
                    symbol_a=arb.symbol,
                    symbol_b=arb.symbol,
                    entry_threshold=arb.entry_threshold,
                    entry_quantity=quantity,
                )
            else:
                await strategy.check_exit(
                    exchange_a_client=client_a,
                    exchange_b_client=client_b,
                    symbol_a=arb.symbol,
                    symbol_b=arb.symbol,
                    exit_threshold=arb.exit_threshold,
                )

            await asyncio.sleep(0.5)

    async with asyncio.TaskGroup() as tg:
        if arb.scenario == "a":
            tg.create_task(_consume_mark_price(client_a, arb.symbol))
            tg.create_task(_consume_spot_price(client_b, arb.symbol))
            tg.create_task(_trade_loop_scenario_a())
        else:
            tg.create_task(_consume_mark_price(client_a, arb.symbol))
            tg.create_task(_consume_mark_price(client_b, arb.symbol))
            tg.create_task(_trade_loop_scenario_b())

    logger.info("runtime stopped")
