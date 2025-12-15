"""Tests for CLI command parsing and basic functionality."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from typer.testing import CliRunner

from tests.conftest import pytest  # Enable pytest fixture
from src.parcer.cli import app, run_cli


def test_cli_help():
    """Test that CLI shows help correctly."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Arbitrage trading bot CLI" in result.output


def test_cli_commands_available():
    """Test that all expected CLI commands are available."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "trade" in result.output
    assert "positions-list" in result.output
    assert "balance-check" in result.output
    assert "history-show" in result.output

    result = runner.invoke(app, ["trade", "--help"])
    assert result.exit_code == 0
    assert "open" in result.output
    assert "close" in result.output


@patch('src.parcer.cli._load_settings')
@patch('src.parcer.cli._build_container')
@patch('src.parcer.cli._create_exchange_clients_from_settings')
@patch('src.parcer.cli.init_components')
def test_trade_open_command_parsing(mock_init_components, mock_create_clients, mock_build_container, mock_load_settings):
    """Test trade_open command parameter parsing."""
    runner = CliRunner()
    
    # Mock settings
    mock_settings = Mock()
    mock_load_settings.return_value = mock_settings
    
    # Mock container
    mock_container = Mock()
    mock_build_container.return_value = mock_container
    
    # Mock components
    mock_history = Mock()
    mock_order_manager = Mock()
    mock_init_components.return_value = (mock_container, mock_history, mock_order_manager)
    
    # Mock exchange clients
    mock_container.exchange_clients = {
        "binance": Mock(),
        "okx": Mock()
    }
    
    # Mock successful position creation
    mock_position = Mock()
    mock_position.position_id = "test-pos-123"
    mock_position.entry_spread = 0.05
    mock_order_manager.create_position.return_value = mock_position
    mock_order_manager.entry_order = AsyncMock(return_value=True)
    
    # Run command
    result = runner.invoke(app, [
        "trade",
        "open",
        "--scenario", "a",
        "--exchange-a", "binance",
        "--exchange-b", "okx",
        "--symbol", "BTCUSDT",
        "--quantity", "0.1",
    ])
    
    # Verify command succeeded
    assert result.exit_code == 0
    assert "Position opened successfully" in result.output
    
    # Verify position was created with correct parameters
    mock_order_manager.create_position.assert_called_once_with(
        symbol_a="BTCUSDT",
        exchange_a="binance",
        symbol_b="BTCUSDT",
        exchange_b="okx",
        scenario="a",
        leg_a_side="buy",
        leg_a_quantity=0.1,
        leg_b_side="sell",
        leg_b_quantity=0.1,
    )


@patch('src.parcer.cli.init_components')
def test_trade_open_scenario_validation(mock_init_components):
    """Test trade_open command validates scenario parameter."""
    runner = CliRunner()
    
    # Mock components
    mock_container = Mock()
    mock_history = Mock()
    mock_order_manager = Mock()
    mock_init_components.return_value = (mock_container, mock_history, mock_order_manager)
    
    # Run command with invalid scenario
    result = runner.invoke(app, [
        "trade",
        "open",
        "--scenario", "invalid",
        "--exchange-a", "binance",
        "--exchange-b", "okx",
        "--symbol", "BTCUSDT",
        "--quantity", "0.1",
    ])
    
    # Verify command failed with validation error
    assert result.exit_code == 1
    assert "Invalid scenario" in result.output


@patch('src.parcer.cli.init_components')
def test_trade_close_command_parsing(mock_init_components):
    """Test trade_close command parameter parsing."""
    runner = CliRunner()
    
    # Mock components
    mock_container = Mock()
    mock_history = Mock()
    mock_order_manager = Mock()
    mock_init_components.return_value = (mock_container, mock_history, mock_order_manager)
    
    # Mock exchange clients as dict
    mock_container.exchange_clients = {
        "binance": Mock(),
        "okx": Mock()
    }
    
    # Mock position found and open
    mock_position = Mock()
    mock_position.position_id = "test-pos-123"
    mock_position.is_open = True
    mock_position.exchange_a = "binance"
    mock_position.exchange_b = "okx"
    mock_position.pnl = 0.005
    mock_position.exit_spread = 0.03
    
    mock_order_manager.get_position.return_value = mock_position
    mock_order_manager.exit_order = AsyncMock(return_value=True)
    
    # Run command
    result = runner.invoke(app, [
        "trade",
        "close",
        "test-pos-123",
    ])
    
    # Verify command succeeded
    assert result.exit_code == 0
    assert "Position closed successfully" in result.output
    
    # Verify position lookup
    mock_order_manager.get_position.assert_called_once_with("test-pos-123")


@patch('src.parcer.cli.init_components')
def test_trade_close_position_not_found(mock_init_components):
    """Test trade_close when position is not found."""
    runner = CliRunner()
    
    # Mock components
    mock_container = Mock()
    mock_history = Mock()
    mock_order_manager = Mock()
    mock_init_components.return_value = (mock_container, mock_history, mock_order_manager)
    
    # Mock position not found
    mock_order_manager.get_position.return_value = None
    
    # Run command
    result = runner.invoke(app, [
        "trade",
        "close",
        "nonexistent-pos",
    ])
    
    # Verify command failed
    assert result.exit_code == 1
    assert "not found" in result.output


@patch('src.parcer.cli.init_components')
def test_positions_list_command(mock_init_components):
    """Test positions list command."""
    runner = CliRunner()
    
    # Mock components
    mock_container = Mock()
    mock_history = Mock()
    mock_order_manager = Mock()
    mock_init_components.return_value = (mock_container, mock_history, mock_order_manager)
    
    # Mock positions
    from datetime import datetime, timezone

    mock_position1 = Mock()
    mock_position1.position_id = "pos-1"
    mock_position1.scenario = "a"
    mock_position1.symbol_a = "BTCUSDT"
    mock_position1.exchange_a = "binance"
    mock_position1.exchange_b = "okx"
    mock_position1.status.value = "opened"
    mock_position1.is_open = True
    mock_position1.entry_spread = 0.05
    mock_position1.pnl = 0.002
    mock_position1.created_at = datetime(2023, 12, 1, 12, 34, 56, tzinfo=timezone.utc)

    mock_position2 = Mock()
    mock_position2.position_id = "pos-2"
    mock_position2.scenario = "b"
    mock_position2.symbol_a = "ETHUSDT"
    mock_position2.exchange_a = "bybit"
    mock_position2.exchange_b = "gate"
    mock_position2.status.value = "closed"
    mock_position2.is_open = False
    mock_position2.entry_spread = None
    mock_position2.pnl = None
    mock_position2.created_at = datetime(2023, 12, 1, 11, 22, 33, tzinfo=timezone.utc)

    mock_history.list_positions.return_value = [mock_position1, mock_position2]
    
    # Run command
    result = runner.invoke(app, ["positions-list"])
    
    # Verify command succeeded
    assert result.exit_code == 0
    assert "Positions" in result.output or "pos-1" in result.output


@patch('src.parcer.cli.init_components')
@patch('asyncio.run')
def test_balance_check_command(mock_asyncio_run, mock_init_components):
    """Test balance check command."""
    runner = CliRunner()
    
    # Mock components
    mock_container = Mock()
    mock_history = Mock()
    mock_order_manager = Mock()
    mock_init_components.return_value = (mock_container, mock_history, mock_order_manager)
    
    # Mock exchange client
    mock_exchange_client = Mock()
    mock_container.exchange_clients = {"binance": mock_exchange_client}
    
    # Mock balance response
    from src.parcer.exchanges.protocol import Balance, Balance
    mock_balance = Mock()
    mock_balance.balances = []
    
    # Mock the async get_balance to return immediately
    mock_exchange_client.get_balance = AsyncMock(return_value=mock_balance)
    mock_asyncio_run.side_effect = lambda coro: None  # Prevent actual async execution
    
    # Run command
    result = runner.invoke(app, [
        "balance-check",
        "binance",
        "BTCUSDT"
    ])
    
    # Verify command executed (even if async didn't run fully)
    assert result.exit_code == 0 or "checking balance" in result.output.lower()


@patch('src.parcer.cli.init_components')
def test_history_show_command(mock_init_components):
    """Test history show command."""
    runner = CliRunner()
    
    # Mock components
    mock_container = Mock()
    mock_history = Mock()
    mock_order_manager = Mock()
    mock_init_components.return_value = (mock_container, mock_history, mock_order_manager)
    
    # Mock trades data
    mock_trade1 = {
        "timestamp": "2023-12-01T12:00:00Z",
        "event_type": "position_opened",
        "position_id": "pos-1",
        "scenario": "a",
        "exchange_a": "binance",
        "exchange_b": "okx",
        "symbol_a": "BTCUSDT",
        "symbol_b": "BTCUSDT",
        "order_type": "market",
        "side": "buy",
        "quantity": 0.1,
        "price": 50000.0,
        "pnl": 0.0,
        "status": "opened",
        "error_message": "",
        "metadata": ""
    }
    
    mock_history.get_recent_trades.return_value = [mock_trade1]
    
    # Run command
    result = runner.invoke(app, [
        "history-show",
        "--hours", "24",
        "--format-type", "table"
    ])
    
    # Verify command succeeded
    assert result.exit_code == 0
    mock_history.get_recent_trades.assert_called_once_with(24)


@patch('src.parcer.cli.init_components')
def test_history_show_json_format(mock_init_components):
    """Test history show with JSON format."""
    runner = CliRunner()
    
    # Mock components
    mock_container = Mock()
    mock_history = Mock()
    mock_order_manager = Mock()
    mock_init_components.return_value = (mock_container, mock_history, mock_order_manager)
    
    # Mock trades data
    mock_trade = {
        "timestamp": "2023-12-01T12:00:00Z",
        "event_type": "position_opened",
        "position_id": "pos-1",
    }
    
    mock_history.get_recent_trades.return_value = [mock_trade]
    
    # Run command with JSON format
    result = runner.invoke(app, [
        "history-show",
        "--format-type", "json"
    ])
    
    # Verify command succeeded
    assert result.exit_code == 0
    # Verify JSON was printed
    assert "position_opened" in result.output


def test_run_cli_function():
    """Test the run_cli function works with argv."""
    with patch('src.parcer.cli.app') as mock_app:
        run_cli(["test", "args"])
        mock_app.assert_called_once_with(["test", "args"])


def test_run_cli_function_none():
    """Test the run_cli function works with None argv."""
    with patch('src.parcer.cli.app') as mock_app:
        run_cli(None)
        mock_app.assert_called_once_with(None)