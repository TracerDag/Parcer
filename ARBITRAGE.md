# Arbitrage Strategy Implementation

This document describes the arbitrage spread detection and execution engine implemented for the parcer bot.

## Overview

The arbitrage module provides automated spread detection and position management for two arbitrage scenarios:

- **Scenario A (Spot vs Futures)**: Long futures + short spot when futures premium exceeds threshold
- **Scenario B (Futures vs Futures)**: Long cheap perpetual + short expensive when spread ≥7%

## Architecture

### Core Components

#### 1. Spread Detection Engine (`src/parcer/strategy/spread_engine.py`)

Detects and calculates spreads between price pairs:

- **`SpreadDetectionEngine`**: Main engine for spread calculation
  - `update_price()`: Cache price updates from exchanges
  - `get_price()`: Retrieve cached prices
  - `calculate_spread()`: Calculate spread between two prices
  - `detect_scenario_a_spread()`: Scenario A specific spread calculation
  - `detect_scenario_b_spread()`: Scenario B specific spread calculation
  - `check_entry_condition()`: Verify if spread meets entry threshold
  - `check_exit_condition()`: Verify if spread has narrowed to exit threshold

**Price Types:**
- `SPOT`: Spot market prices
- `MARK`: Perpetual/futures mark prices

#### 2. Position Management (`src/parcer/orders/position.py`)

Tracks position lifecycle:

- **`Position`**: Represents a two-leg arbitrage position
  - `position_id`: Unique identifier
  - `status`: `PENDING → OPENED → CLOSING → CLOSED` or `ERROR`
  - `leg_a_side`/`leg_b_side`: Buy/sell sides for each leg
  - `entry_price_a`/`entry_price_b`: Entry prices for each leg
  - `entry_spread`: Spread at entry time
  - `pnl`: Profit/loss calculation

- **`PositionStatus`**: Enum for position state

#### 3. Order Manager (`src/parcer/orders/manager.py`)

Coordinates entry and exit orders:

- **`OrderManager`**: Manages position lifecycle
  - `create_position()`: Create new position
  - `get_position()`: Retrieve position by ID
  - `get_active_positions()`: Get all open positions
  - `entry_order()`: Execute entry orders for both legs
  - `exit_order()`: Execute exit orders to close position

#### 4. Strategy Implementations

##### Scenario A (`src/parcer/strategy/scenario_a.py`)

Spot vs Futures arbitrage:

- **Entry**: Long futures + short spot when futures premium > entry_threshold
- **Exit**: Close when spread narrows below exit_threshold
- **Configuration**:
  - `entry_threshold`: Minimum premium (default: 5%)
  - `exit_threshold`: Maximum spread to trigger exit (default: 1%)

```python
strategy = ScenarioAStrategy(spread_engine, order_manager)

position = await strategy.check_entry(
    futures_client,
    spot_client,
    "BTCUSDT",  # futures symbol
    "BTCUSDT",  # spot symbol
    entry_threshold=0.05,
    entry_quantity=1.0
)

if position:
    closed = await strategy.check_exit(
        futures_client,
        spot_client,
        exit_threshold=0.01
    )
```

##### Scenario B (`src/parcer/strategy/scenario_b.py`)

Futures vs Futures arbitrage:

- **Entry**: Long cheap perpetual + short expensive when spread >= entry_threshold
- **Exit**: Close when spread drops below exit_threshold
- **Configuration**:
  - `entry_threshold`: Minimum spread (default: 7%)
  - `exit_threshold`: Maximum spread to trigger exit (default: 1%)

```python
strategy = ScenarioBStrategy(spread_engine, order_manager)

position = await strategy.check_entry(
    exchange_a_client,
    exchange_b_client,
    "BTCUSDT",  # symbol on exchange A
    "BTCUSDT",  # symbol on exchange B
    entry_threshold=0.07,
    entry_quantity=1.0
)

if position:
    closed = await strategy.check_exit(
        exchange_a_client,
        exchange_b_client,
        "BTCUSDT",
        "BTCUSDT",
        exit_threshold=0.01
    )
```

## Configuration

### YAML Configuration

```yaml
arbitrage:
  enabled: true
  scenario: a                 # "a" for spot-vs-futures, "b" for futures-vs-futures
  entry_threshold: 0.05       # Entry spread threshold (5% for scenario A, 7% for B)
  exit_threshold: 0.01        # Exit spread threshold (1%)
  exchange_a: binance_futures # First exchange
  exchange_b: binance_spot    # Second exchange
  symbol: BTCUSDT             # Trading symbol
```

### Environment Variables

Using `PARCER_` prefix with `__` for nesting:

```bash
export PARCER_ARBITRAGE__ENABLED=true
export PARCER_ARBITRAGE__SCENARIO=a
export PARCER_ARBITRAGE__ENTRY_THRESHOLD=0.05
export PARCER_ARBITRAGE__EXIT_THRESHOLD=0.01
export PARCER_ARBITRAGE__EXCHANGE_A=binance_futures
export PARCER_ARBITRAGE__EXCHANGE_B=binance_spot
export PARCER_ARBITRAGE__SYMBOL=BTCUSDT
```

## Key Features

### 1. Duplicate Token Validation

Before entry, the strategy validates that symbols match across exchanges:

```python
from parcer.exchanges.normalization import check_symbol_mismatch

# Logs warnings if symbols don't match (e.g., BTCUSDT vs BTC-USDT)
check_symbol_mismatch("BTCUSDT", "BTCUSDT")
```

Handles multiple symbol formats:
- BTCUSDT (Binance format)
- BTC-USDT (Bybit format)
- BTC/USDT (Alternative format)

### 2. Position Lifecycle Tracking

Each position tracks:

- **Creation**: When position is created (PENDING status)
- **Entry**: When both legs are filled (OPENED status)
- **Exit**: When position is closed (CLOSED status)
- **Timestamps**: created_at, opened_at, closed_at
- **PnL**: Calculated upon exit

```python
position.mark_opened(entry_price_a, entry_price_b)
# ... position is open ...
position.mark_closed(exit_price_a, exit_price_b)
print(f"PnL: {position.pnl}")
```

### 3. Spread Calculation

**Scenario A (Spot vs Futures):**
```
spread = (futures_price - spot_price) / spot_price
```
- Positive spread: Futures premium
- Negative spread: Spot premium

**Scenario B (Futures vs Futures):**
```
spread = (expensive_price - cheap_price) / cheap_price
```
- Always calculated from cheaper to more expensive

### 4. Entry/Exit Logic

**Entry Conditions:**
- Scenario A: `|spread| >= entry_threshold`
- Scenario B: `|spread| >= entry_threshold`

**Exit Conditions:**
- Scenario A: `|spread| <= exit_threshold`
- Scenario B: `|spread| <= exit_threshold`

### 5. Error Handling

- Failed orders mark position as ERROR
- Missing prices prevent entry/exit
- Exception logging for debugging
- Graceful degradation

## Testing

### Test Coverage

- **66 unit/integration tests** for arbitrage components
- **128 total tests** including existing exchange tests

### Test Modules

1. **`tests/test_spread_engine.py`** (19 tests)
   - Spread calculation accuracy
   - Entry/exit condition logic
   - Synthetic price stream handling

2. **`tests/test_position.py`** (11 tests)
   - Position lifecycle
   - Spread calculation on open/close
   - PnL calculations

3. **`tests/test_order_manager.py`** (10 tests)
   - Position creation and retrieval
   - Entry/exit order execution
   - Error handling

4. **`tests/test_scenario_strategies.py`** (18 tests)
   - Scenario A entry/exit logic
   - Scenario B entry/exit logic
   - Duplicate token validation

5. **`tests/test_arbitrage_simulation.py`** (8 tests)
   - End-to-end simulations with synthetic prices
   - Multiple entry attempts
   - High volatility scenarios
   - Continuous price stream updates

### Running Tests

```bash
# All arbitrage tests
pytest tests/test_spread_engine.py tests/test_position.py \
        tests/test_order_manager.py tests/test_scenario_strategies.py \
        tests/test_arbitrage_simulation.py -v

# All tests including existing
pytest tests/ -v

# Specific test
pytest tests/test_scenario_strategies.py::TestScenarioAStrategy::test_exit_success -v
```

## Usage Example

### Scenario A (Spot vs Futures)

```python
import asyncio
from parcer.strategy.spread_engine import SpreadDetectionEngine, PriceType
from parcer.strategy.scenario_a import ScenarioAStrategy
from parcer.orders.manager import OrderManager
from parcer.exchanges.factory import create_exchange_client

async def main():
    # Initialize components
    spread_engine = SpreadDetectionEngine()
    order_manager = OrderManager()
    strategy = ScenarioAStrategy(spread_engine, order_manager)
    
    # Create exchange clients
    futures_client = create_exchange_client("binance", api_key, api_secret)
    spot_client = create_exchange_client("binance", api_key, api_secret)
    
    # Simulate price updates
    spread_engine.update_price(
        "binance_futures", "BTCUSDT", 50000.0, price_type=PriceType.MARK
    )
    spread_engine.update_price(
        "binance_spot", "BTCUSDT", 45000.0, price_type=PriceType.SPOT
    )
    
    # Check for entry
    position = await strategy.check_entry(
        futures_client,
        spot_client,
        "BTCUSDT",
        "BTCUSDT",
        entry_threshold=0.05,
        entry_quantity=1.0
    )
    
    if position:
        print(f"Position opened: {position.position_id}")
        print(f"Entry spread: {position.entry_spread*100:.2f}%")
    
    # Later: update prices and check for exit
    spread_engine.update_price(
        "binance_futures", "BTCUSDT", 45500.0, price_type=PriceType.MARK
    )
    spread_engine.update_price(
        "binance_spot", "BTCUSDT", 45400.0, price_type=PriceType.SPOT
    )
    
    closed = await strategy.check_exit(
        futures_client,
        spot_client,
        exit_threshold=0.01
    )
    
    if closed:
        print(f"Position closed: PnL={position.pnl}")

asyncio.run(main())
```

## Logging

Strategy decisions are logged at INFO level:

```
INFO: Created position pos_123: BTCUSDT@binance_futures vs BTCUSDT@binance_spot (scenario a)
INFO: Scenario A entry signal: 5.2% premium on futures
INFO: Position pos_123 opened with spread 5.15%
INFO: Scenario A exit signal: spread narrowed to 0.8%
INFO: Position pos_123 closed with exit spread 0.75% PnL: 0.000145
```

Debug logging available at DEBUG level for spread calculations and price updates.

## Future Enhancements

- WebSocket-based real-time price streaming
- Multi-position concurrent management
- Position sizing algorithms
- Risk management (stop-loss, max loss)
- Historical backtest support
- Performance metrics and analytics
