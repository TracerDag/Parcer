"""Trade and order history tracking with CSV and SQLite storage."""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .orders.position import Position, PositionStatus
from .orders.manager import OrderStatus

logger = logging.getLogger(__name__)


class TradeHistory:
    """Manages trade and order history in CSV and SQLite formats."""

    def __init__(self, data_dir: Path | None = None) -> None:
        """Initialize trade history manager."""
        self.data_dir = data_dir or Path("data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.csv_file = self.data_dir / "trades.csv"
        self.sqlite_file = self.data_dir / "trades.db"
        self._init_csv()
        self._init_sqlite()
        
        # Clean old records (keep only last 24h in SQLite)
        self._cleanup_old_records()

    def _init_csv(self) -> None:
        """Initialize CSV file with headers if it doesn't exist."""
        if not self.csv_file.exists():
            with open(self.csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "event_type",
                    "position_id",
                    "scenario",
                    "exchange_a",
                    "exchange_b",
                    "symbol_a",
                    "symbol_b",
                    "order_type",
                    "side",
                    "quantity",
                    "price",
                    "pnl",
                    "status",
                    "error_message",
                    "metadata"
                ])

    def _init_sqlite(self) -> None:
        """Initialize SQLite database with tables."""
        with sqlite3.connect(self.sqlite_file) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    position_id TEXT,
                    scenario TEXT,
                    exchange_a TEXT,
                    exchange_b TEXT,
                    symbol_a TEXT,
                    symbol_b TEXT,
                    order_type TEXT,
                    side TEXT,
                    quantity REAL,
                    price REAL,
                    pnl REAL,
                    status TEXT,
                    error_message TEXT,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON trades(timestamp)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_position_id 
                ON trades(position_id)
            """)

    def _cleanup_old_records(self) -> None:
        """Remove records older than 24 hours from SQLite."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        
        with sqlite3.connect(self.sqlite_file) as conn:
            conn.execute(
                "DELETE FROM trades WHERE timestamp < ?",
                (cutoff_time.isoformat(),)
            )
            logger.debug("Cleaned up SQLite records older than 24h")

    def record_trade_event(
        self,
        event_type: str,
        position: Position,
        order_type: str = "",
        side: str = "",
        quantity: float = 0.0,
        price: float = 0.0,
        pnl: float = 0.0,
        status: str = "",
        error_message: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """Record a trade event in both CSV and SQLite."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Prepare record data
        record = {
            "timestamp": timestamp,
            "event_type": event_type,
            "position_id": position.position_id,
            "scenario": position.scenario,
            "exchange_a": position.exchange_a,
            "exchange_b": position.exchange_b,
            "symbol_a": position.symbol_a,
            "symbol_b": position.symbol_b,
            "order_type": order_type,
            "side": side,
            "quantity": quantity,
            "price": price,
            "pnl": pnl,
            "status": status,
            "error_message": error_message,
            "metadata": json.dumps(metadata) if metadata else "",
        }

        # Record to CSV (append)
        self._record_to_csv(record)
        
        # Record to SQLite
        self._record_to_sqlite(record)

    def _record_to_csv(self, record: Dict[str, Any]) -> None:
        """Record event to CSV file."""
        try:
            with open(self.csv_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=record.keys())
                writer.writerow(record)
        except Exception as e:
            logger.error("Failed to write to CSV: %s", e)

    def _record_to_sqlite(self, record: Dict[str, Any]) -> None:
        """Record event to SQLite database."""
        try:
            with sqlite3.connect(self.sqlite_file) as conn:
                conn.execute("""
                    INSERT INTO trades (
                        timestamp, event_type, position_id, scenario,
                        exchange_a, exchange_b, symbol_a, symbol_b,
                        order_type, side, quantity, price, pnl,
                        status, error_message, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record["timestamp"], record["event_type"], record["position_id"],
                    record["scenario"], record["exchange_a"], record["exchange_b"],
                    record["symbol_a"], record["symbol_b"], record["order_type"],
                    record["side"], record["quantity"], record["price"], record["pnl"],
                    record["status"], record["error_message"], record["metadata"]
                ))
        except Exception as e:
            logger.error("Failed to write to SQLite: %s", e)

    def record_position_created(self, position: Position) -> None:
        """Record position creation."""
        self.record_trade_event(
            event_type="position_created",
            position=position,
            status=position.status.value,
            metadata={"leg_a_quantity": position.leg_a_quantity,
                     "leg_b_quantity": position.leg_b_quantity}
        )
        logger.info("Recorded position creation: %s", position.position_id)

    def record_position_opened(self, position: Position) -> None:
        """Record position opening with entry prices."""
        self.record_trade_event(
            event_type="position_opened",
            position=position,
            status="opened",
            price=position.entry_spread or 0.0,
            metadata={"entry_price_a": position.entry_price_a,
                     "entry_price_b": position.entry_price_b}
        )
        logger.info("Recorded position opening: %s", position.position_id)

    def record_position_closed(self, position: Position) -> None:
        """Record position closing with exit prices and PnL."""
        self.record_trade_event(
            event_type="position_closed",
            position=position,
            pnl=position.pnl or 0.0,
            status="closed",
            metadata={"exit_spread": position.exit_spread}
        )
        logger.info("Recorded position closing: %s PnL: %.6f", 
                   position.position_id, position.pnl or 0)

    def record_position_error(self, position: Position, error_message: str) -> None:
        """Record position error."""
        self.record_trade_event(
            event_type="position_error",
            position=position,
            status="error",
            error_message=error_message
        )
        logger.error("Recorded position error: %s - %s", 
                    position.position_id, error_message)

    def record_order_placed(
        self,
        position: Position,
        order_side: str,
        order_type: str,
        quantity: float,
        price: float,
    ) -> None:
        """Record order placement."""
        self.record_trade_event(
            event_type="order_placed",
            position=position,
            order_type=order_type,
            side=order_side,
            quantity=quantity,
            price=price
        )
        logger.debug("Recorded order placement: %s %s %s @ %s", 
                    order_side, quantity, order_type, price)

    def record_insufficient_balance(
        self,
        exchange: str,
        symbol: str,
        required: float,
        available: float,
    ) -> None:
        """Record insufficient balance alert."""
        event_type = "insufficient_balance"
        
        # Create a minimal position record for the alert
        position = Position(
            position_id="ALERT",
            symbol_a=symbol,
            exchange_a=exchange,
            symbol_b="",
            exchange_b="",
            scenario="alert",
            leg_a_side="",
            leg_a_quantity=0.0,
            leg_b_side="",
            leg_b_quantity=0.0,
        )
        
        self.record_trade_event(
            event_type=event_type,
            position=position,
            metadata={
                "exchange": exchange,
                "symbol": symbol,
                "required": required,
                "available": available,
                "shortfall": required - available
            }
        )
        logger.warning("Recorded insufficient balance alert: %s %s required %s available %s",
                      exchange, symbol, required, available)

    def get_recent_trades(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent trades from SQLite (last N hours)."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        with sqlite3.connect(self.sqlite_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM trades 
                WHERE timestamp > ?
                ORDER BY timestamp DESC
            """, (cutoff_time.isoformat(),))
            
            return [dict(row) for row in cursor.fetchall()]

    def get_position_history(self, position_id: str) -> List[Dict[str, Any]]:
        """Get all events for a specific position."""
        with sqlite3.connect(self.sqlite_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM trades 
                WHERE position_id = ?
                ORDER BY timestamp
            """, (position_id,))
            
            return [dict(row) for row in cursor.fetchall()]