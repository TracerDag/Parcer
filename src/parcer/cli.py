"""Typer-based CLI for arbitrage bot operations."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel

if TYPE_CHECKING:
    from .di import AppContainer
    from .history import TradeHistory
    from .orders.manager import OrderManager
    from .orders.position import Position

# Import with local function to avoid circular imports
def _load_settings(config_path: Optional[Path] = None):
    from .config import load_settings
    return load_settings(config_path)

def _build_container(settings, exchange_clients):
    from .di import build_container
    return build_container(settings, exchange_clients)

def _create_exchange_clients_from_settings(settings):
    from .exchanges.init import create_exchange_clients_from_settings
    return create_exchange_clients_from_settings(settings)

def _configure_logging(log_dir: Path | None = None):
    from .logging import configure_logging
    return configure_logging(log_dir)

app = typer.Typer(help="Arbitrage trading bot CLI")
console = Console()
logger = logging.getLogger(__name__)


def run_cli(argv: list[str] | None = None) -> None:
    """Run CLI with optional argv parameter."""
    app(argv)


def init_components(config_path: Optional[Path] = None):
    """Initialize core components."""
    settings = _load_settings(config_path)
    
    # Create exchange clients from settings
    exchange_clients = _create_exchange_clients_from_settings(settings)
    
    # Build container with exchange clients
    container = _build_container(settings, exchange_clients)
    
    # Configure logging
    log_dir = Path("logs")
    _configure_logging(log_dir)
    
    # Initialize history and order manager
    from .history import TradeHistory
    from .orders.manager import OrderManager
    
    data_dir = Path("data")
    history = TradeHistory(data_dir)
    order_manager = OrderManager(settings, history)
    
    return container, history, order_manager


@app.command()
def trade_open(
    scenario: str = typer.Option(..., help="Arbitrage scenario (a or b)"),
    exchange_a: str = typer.Option(..., help="First exchange"),
    exchange_b: str = typer.Option(..., help="Second exchange"),
    symbol: str = typer.Option(..., help="Trading symbol"),
    quantity: float = typer.Option(..., help="Trade quantity"),
    config: Optional[Path] = typer.Option(None, help="Path to config file"),
) -> None:
    """Open a new arbitrage position."""
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Opening position...", total=None)
            
            # Run async operation
            success = asyncio.run(_open_position_async(scenario, exchange_a, exchange_b, symbol, quantity, config, progress, task))
            
            if not success:
                raise typer.Exit(1)
                
    except Exception as e:
        logger.error("Failed to open position: %s", e, exc_info=True)
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


async def _open_position_async(scenario: str, exchange_a: str, exchange_b: str, symbol: str, quantity: float, config: Optional[Path], progress: Progress, task) -> bool:
    """Async implementation of position opening."""
    container, history, order_manager = init_components(config)
    
    # Validate scenario
    if scenario not in ["a", "b"]:
        console.print(f"[red]Error:[/red] Invalid scenario '{scenario}'. Must be 'a' or 'b'.")
        return False
    
    progress.update(task, description="Creating position...")
    
    try:
        # Create position
        position = order_manager.create_position(
            symbol_a=symbol,
            exchange_a=exchange_a,
            symbol_b=symbol,
            exchange_b=exchange_b,
            scenario=scenario,
            leg_a_side="buy",
            leg_a_quantity=quantity,
            leg_b_side="sell",
            leg_b_quantity=quantity,
        )
        
        # Record position creation
        history.record_position_created(position)
        
        progress.update(task, description="Placing orders...")
        
        # Check if exchange clients are available
        if exchange_a not in container.exchange_clients:
            console.print(f"[red]Error:[/red] Exchange '{exchange_a}' not configured")
            history.record_position_error(position, f"Exchange {exchange_a} not configured")
            return False
            
        if exchange_b not in container.exchange_clients:
            console.print(f"[red]Error:[/red] Exchange '{exchange_b}' not configured")
            history.record_position_error(position, f"Exchange {exchange_b} not configured")
            return False
        
        # Get exchange clients
        exchange_client_a = container.exchange_clients[exchange_a]
        exchange_client_b = container.exchange_clients[exchange_b]
        
        # Execute entry orders
        success = await order_manager.entry_order(
            position, exchange_client_a, exchange_client_b, history
        )
        
        if success:
            # Record position opening
            history.record_position_opened(position)
            
            spread_str = f"{position.entry_spread * 100:.4f}%" if position.entry_spread else "N/A"
            
            console.print(Panel.fit(
                f"[green]✓ Position opened successfully![/green]\n"
                f"Position ID: {position.position_id}\n"
                f"Scenario: {scenario}\n"
                f"Symbol: {symbol}\n"
                f"Quantity: {quantity}\n"
                f"Entry Spread: {spread_str}",
                title="Trade Open"
            ))
            return True
        else:
            # Record error
            history.record_position_error(position, "Failed to place entry orders")
            console.print("[red]✗ Failed to open position[/red]")
            return False
            
    except Exception as e:
        logger.error("Failed in position opening: %s", e, exc_info=True)
        console.print(f"[red]Error:[/red] {e}")
        return False


@app.command()
def trade_close(
    position_id: str = typer.Argument(..., help="Position ID to close"),
    config: Optional[Path] = typer.Option(None, help="Path to config file"),
) -> None:
    """Close an existing arbitrage position."""
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Closing position...", total=None)
            
            # Run async operation
            success = asyncio.run(_close_position_async(position_id, config, progress, task))
            
            if not success:
                raise typer.Exit(1)
                
    except Exception as e:
        logger.error("Failed to close position: %s", e, exc_info=True)
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


async def _close_position_async(position_id: str, config: Optional[Path], progress: Progress, task) -> bool:
    """Async implementation of position closing."""
    container, history, order_manager = init_components(config)
    
    try:
        # Find position
        position = order_manager.get_position(position_id)
        if not position:
            console.print(f"[red]Error:[/red] Position {position_id} not found")
            return False
        
        if not position.is_open:
            console.print(f"[red]Error:[/red] Position {position_id} is not open")
            return False
        
        progress.update(task, description="Placing exit orders...")
        
        # Get exchange clients
        exchange_client_a = container.exchange_clients[position.exchange_a]
        exchange_client_b = container.exchange_clients[position.exchange_b]
        
        # Execute exit orders
        success = await order_manager.exit_order(
            position, exchange_client_a, exchange_client_b, history
        )
        
        if success:
            # Record position closing
            history.record_position_closed(position)
            
            pnl_str = f"{position.pnl:.6f}" if position.pnl else "0.000000"
            spread_str = f"{position.exit_spread * 100:.4f}%" if position.exit_spread else "N/A"
            
            console.print(Panel.fit(
                f"[green]✓ Position closed successfully![/green]\n"
                f"Position ID: {position.position_id}\n"
                f"Exit Spread: {spread_str}\n"
                f"PnL: {pnl_str}",
                title="Trade Close"
            ))
            return True
        else:
            console.print("[red]✗ Failed to close position[/red]")
            return False
            
    except Exception as e:
        logger.error("Failed in position closing: %s", e, exc_info=True)
        console.print(f"[red]Error:[/red] {e}")
        return False


@app.command()
def positions_list(
    config: Optional[Path] = typer.Option(None, help="Path to config file"),
    status: Optional[str] = typer.Option(None, help="Filter by status (open/closed/error)"),
) -> None:
    """List all positions."""
    
    try:
        _, _, order_manager = init_components(config)
        
        positions = order_manager.get_active_positions() if status == "open" else list(order_manager.positions.values())
        
        if status:
            positions = [p for p in positions if p.status.value == status]
        
        if not positions:
            console.print("[yellow]No positions found[/yellow]")
            return
        
        # Create table
        table = Table(title="Positions")
        table.add_column("Position ID", style="cyan")
        table.add_column("Scenario", style="magenta")
        table.add_column("Symbol", style="green")
        table.add_column("Exchanges", style="blue")
        table.add_column("Status", style="yellow")
        table.add_column("Entry Spread", style="red")
        table.add_column("PnL", style="green")
        table.add_column("Created", style="dim")
        
        for position in sorted(positions, key=lambda p: p.created_at):
            spread_str = f"{position.entry_spread * 100:.4f}%" if position.entry_spread else "N/A"
            pnl_str = f"{position.pnl:.6f}" if position.pnl else "0.000000"
            exchanges = f"{position.exchange_a} vs {position.exchange_b}"
            created_str = position.created_at.strftime("%H:%M:%S")
            
            # Color code status
            status_style = {
                "open": "green",
                "closed": "blue", 
                "error": "red",
                "closing": "yellow",
            }.get(position.status.value, "white")
            
            table.add_row(
                position.position_id[:8] + "...",
                position.scenario.upper(),
                position.symbol_a,
                exchanges,
                f"[{status_style}]{position.status.value.upper()}[/{status_style}]",
                spread_str,
                pnl_str,
                created_str,
            )
        
        console.print(table)
        
        # Summary stats
        open_positions = [p for p in positions if p.is_open]
        total_pnl = sum(p.pnl or 0 for p in positions)
        
        console.print(f"\n[bold]Summary:[/bold] {len(open_positions)} open, {len(positions)} total, Total PnL: {total_pnl:.6f}")
        
    except Exception as e:
        logger.error("Failed to list positions: %s", e, exc_info=True)
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def balance_check(
    exchange: str = typer.Argument(..., help="Exchange to check"),
    symbol: str = typer.Argument(..., help="Symbol to check"),
    config: Optional[Path] = typer.Option(None, help="Path to config file"),
) -> None:
    """Check balance for a specific exchange and symbol."""
    
    try:
        # Run async operation
        asyncio.run(_check_balance_async(exchange, symbol, config))
                
    except Exception as e:
        logger.error("Failed to check balance: %s", e, exc_info=True)
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


async def _check_balance_async(exchange: str, symbol: str, config: Optional[Path]) -> None:
    """Async implementation of balance checking."""
    container, history, _ = init_components(config)
    
    console.print(f"Checking balance on [cyan]{exchange}[/cyan] for [green]{symbol}[/green]...")
    
    try:
        # Get exchange client
        if exchange not in container.exchange_clients:
            console.print(f"[red]Error:[/red] Exchange '{exchange}' not configured")
            return
        
        exchange_client = container.exchange_clients[exchange]
        
        # Get balance
        balance = await exchange_client.get_balance()
        
        # Find balance for symbol
        symbol_balance = 0.0
        base_asset = symbol.replace("USDT", "").replace("USDC", "").replace("BUSD", "")
        for asset_balance in balance.balances:
            if asset_balance.asset == base_asset:
                symbol_balance = asset_balance.free
                break
        
        console.print(Panel.fit(
            f"Exchange: [cyan]{exchange}[/cyan]\n"
            f"Symbol: [green]{symbol}[/green]\n"
            f"Available Balance: [bold]{symbol_balance:.6f}[/bold]",
            title="Balance Check"
        ))
        
        # Log balance check
        logger.info("Balance check: %s %s = %s", exchange, symbol, symbol_balance)
        
        # Check if balance is sufficient (assuming minimum 10 units)
        min_required = 10.0
        if symbol_balance < min_required:
            history.record_insufficient_balance(
                exchange=exchange,
                symbol=symbol,
                required=min_required,
                available=symbol_balance,
            )
            console.print(f"[yellow]⚠ Warning: Insufficient balance. Required: {min_required}, Available: {symbol_balance:.6f}[/yellow]")
        
    except Exception as e:
        logger.error("Failed to check balance: %s", e, exc_info=True)
        console.print(f"[red]Error:[/red] {e}")


@app.command()
def history_show(
    hours: int = typer.Option(24, help="Show history from last N hours"),
    format_type: str = typer.Option("table", help="Output format (table/json/csv)"),
) -> None:
    """Show trade history."""
    
    try:
        _, history, _ = init_components()
        
        trades = history.get_recent_trades(hours)
        
        if not trades:
            console.print(f"[yellow]No trades found in the last {hours} hours[/yellow]")
            return
        
        if format_type == "json":
            import json
            console.print_json(json.dumps(trades, indent=2))
        elif format_type == "csv":
            # Simple CSV output
            console.print("timestamp,event_type,position_id,scenario,exchange_a,exchange_b,symbol_a,symbol_b,order_type,side,quantity,price,pnl,status")
            for trade in trades:
                console.print(f"{trade['timestamp']},{trade['event_type']},{trade['position_id']},{trade['scenario']},{trade['exchange_a']},{trade['exchange_b']},{trade['symbol_a']},{trade['symbol_b']},{trade['order_type']},{trade['side']},{trade['quantity']},{trade['price']},{trade['pnl']},{trade['status']}")
        else:
            # Table format
            table = Table(title=f"Trade History (Last {hours} Hours)")
            table.add_column("Timestamp", style="dim")
            table.add_column("Event", style="cyan")
            table.add_column("Position ID", style="magenta")
            table.add_column("Scenario", style="yellow")
            table.add_column("Exchanges", style="blue")
            table.add_column("Symbol", style="green")
            table.add_column("Type", style="red")
            table.add_column("Side", style="cyan")
            table.add_column("Quantity", style="magenta")
            table.add_column("Price", style="yellow")
            table.add_column("PnL", style="green")
            table.add_column("Status", style="white")
            
            for trade in trades:
                table.add_row(
                    trade['timestamp'][-8:] if trade['timestamp'] else "",  # Just time part
                    trade['event_type'],
                    (trade['position_id'][:8] + "...") if trade['position_id'] and len(trade['position_id']) > 8 else (trade['position_id'] or ""),
                    trade['scenario'] or "",
                    f"{trade['exchange_a']} vs {trade['exchange_b']}" if trade['exchange_a'] and trade['exchange_b'] else trade['exchange_a'] or trade['exchange_b'] or "",
                    trade['symbol_a'] or trade['symbol_b'] or "",
                    trade['order_type'] or "",
                    trade['side'] or "",
                    f"{float(trade['quantity']):.6f}" if trade['quantity'] else "",
                    f"{float(trade['price']):.6f}" if trade['price'] else "",
                    f"{float(trade['pnl']):.6f}" if trade['pnl'] else "",
                    trade['status'] or "",
                )
            
            console.print(table)
            
        console.print(f"\n[bold]Total records:[/bold] {len(trades)}")
        
    except Exception as e:
        logger.error("Failed to show history: %s", e, exc_info=True)
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def main():
    """CLI main entry point."""
    app()


if __name__ == "__main__":
    main()