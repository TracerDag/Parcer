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
            metadata={
                "leg_a_side": position.leg_a_side,
                "leg_a_quantity": position.leg_a_quantity,
                "leg_b_side": position.leg_b_side,
                "leg_b_quantity": position.leg_b_quantity,
            },
        )
        logger.info("Recorded position creation: %s", position.position_id)

    def record_position_opened(self, position: Position) -> None:
        """Record position opening with entry prices."""
        self.record_trade_event(
            event_type="position_opened",
            position=position,
            status="opened",
            price=position.entry_spread or 0.0,
            metadata={
                "entry_price_a": position.entry_price_a,
                "entry_price_b": position.entry_price_b,
                "leg_a_order_id": position.leg_a_order_id,
                "leg_b_order_id": position.leg_b_order_id,
            },
        )
        logger.info("Recorded position opening: %s", position.position_id)

    def record_position_closed(self, position: Position) -> None:
        """Record position closing with exit prices and PnL."""
        self.record_trade_event(
            event_type="position_closed",
            position=position,
            pnl=position.pnl or 0.0,
            status="closed",
            metadata={"exit_spread": position.exit_spread},
        )
        logger.info(
            "Recorded position closing: %s PnL: %.6f",
            position.position_id,
            position.pnl or 0,
        )

    def record_position_error(self, position: Position, error_message: str) -> None:
        """Record position error."""
        self.record_trade_event(
            event_type="position_error",
            position=position,
            status="error",
            error_message=error_message,
        )
        logger.error(
            "Recorded position error: %s - %s", position.position_id, error_message
        )

    def record_order_placed(
        self,
        position: Position,
        order_side: str,
        order_type: str,
        quantity: float,
        price: float,
        *,
        order_id: str | None = None,
        exchange: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
        phase: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """Record order placement."""
        md: Dict[str, Any] = {}
        if metadata:
            md.update(metadata)
        if order_id is not None:
            md["order_id"] = order_id
        if exchange is not None:
            md["exchange"] = exchange
        if symbol is not None:
            md["symbol"] = symbol
        if status is not None:
            md["order_status"] = status
        if phase is not None:
            md["phase"] = phase

        self.record_trade_event(
            event_type="order_placed",
            position=position,
            order_type=order_type,
            side=order_side,
            quantity=quantity,
            price=price,
            metadata=md or None,
        )
        logger.debug(
            "Recorded order placement: %s %s %s @ %s", order_side, quantity, order_type, price
        )

    def record_order_rollback(
        self,
        position: Position,
        *,
        original_order_id: str | None,
        rollback_order_id: str | None,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        status: str | None,
        reason: str,
    ) -> None:
        self.record_trade_event(
            event_type="order_rollback",
            position=position,
            order_type="market",
            side=side,
            quantity=quantity,
            price=price,
            status=status or "",
            metadata={
                "exchange": exchange,
                "symbol": symbol,
                "reason": reason,
                "original_order_id": original_order_id,
                "rollback_order_id": rollback_order_id,
            },
        )

    def record_order_failed(
        self,
        position: Position,
        *,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        phase: str,
        error_message: str,
    ) -> None:
        self.record_trade_event(
            event_type="order_failed",
            position=position,
            order_type="market",
            side=side,
            quantity=quantity,
            error_message=error_message,
            metadata={"exchange": exchange, "symbol": symbol, "phase": phase},
        )

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
            cursor = conn.execute(
                """
                SELECT * FROM trades 
                WHERE position_id = ?
                ORDER BY timestamp
            """,
                (position_id,),
            )

            return [dict(row) for row in cursor.fetchall()]

    def load_position(self, position_id: str) -> Position | None:
        """Reconstruct a Position from persisted history."""
        events = self.get_position_history(position_id)
        if not events:
            return None

        created = next((e for e in events if e.get("event_type") == "position_created"), None)
        if created is None:
            return None

        created_md = self._parse_metadata(created.get("metadata"))

        position = Position(
            position_id=created.get("position_id") or position_id,
            symbol_a=created.get("symbol_a") or "",
            exchange_a=created.get("exchange_a") or "",
            symbol_b=created.get("symbol_b") or "",
            exchange_b=created.get("exchange_b") or "",
            scenario=created.get("scenario") or "",
            leg_a_side=created_md.get("leg_a_side") or "",
            leg_a_quantity=float(created_md.get("leg_a_quantity") or 0.0),
            leg_b_side=created_md.get("leg_b_side") or "",
            leg_b_quantity=float(created_md.get("leg_b_quantity") or 0.0),
        )

        position.created_at = (
            self._parse_timestamp(created.get("timestamp")) or position.created_at
        )

        lifecycle = [
            e
            for e in events
            if e.get("event_type")
            in {"position_created", "position_opened", "position_closed", "position_error"}
        ]
        latest_lifecycle = lifecycle[-1] if lifecycle else created
        latest_status = latest_lifecycle.get("status")
        if latest_status:
            try:
                position.status = PositionStatus(latest_status)
            except ValueError:
                pass

        opened = next(
            (e for e in reversed(lifecycle) if e.get("event_type") == "position_opened"),
            None,
        )
        if opened is not None:
            opened_md = self._parse_metadata(opened.get("metadata"))
            position.opened_at = self._parse_timestamp(opened.get("timestamp"))
            position.entry_spread = float(opened.get("price") or 0.0)
            position.entry_price_a = float(opened_md.get("entry_price_a") or 0.0)
            position.entry_price_b = float(opened_md.get("entry_price_b") or 0.0)
            position.leg_a_order_id = opened_md.get("leg_a_order_id")
            position.leg_b_order_id = opened_md.get("leg_b_order_id")

        closed = next(
            (e for e in reversed(lifecycle) if e.get("event_type") == "position_closed"),
            None,
        )
        if closed is not None:
            closed_md = self._parse_metadata(closed.get("metadata"))
            position.closed_at = self._parse_timestamp(closed.get("timestamp"))
            position.exit_spread = closed_md.get("exit_spread")
            position.pnl = closed.get("pnl")

        return position

    def list_positions(self, *, status: str | None = None) -> list[Position]:
        """List positions reconstructed from history."""
        with sqlite3.connect(self.sqlite_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT DISTINCT position_id
                FROM trades
                WHERE position_id IS NOT NULL
                  AND position_id != ''
                  AND position_id != 'ALERT'
            """
            )
            position_ids = [row["position_id"] for row in cursor.fetchall()]

        positions: list[Position] = []
        for pid in position_ids:
            position = self.load_position(pid)
            if position is None:
                continue
            if status is not None and position.status.value != status:
                continue
            positions.append(position)

        return positions

    def count_open_positions(self) -> int:
        """Count positions whose latest lifecycle status is OPENED."""
        lifecycle_events = (
            "position_created",
            "position_opened",
            "position_closed",
            "position_error",
        )

        with sqlite3.connect(self.sqlite_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT t1.position_id, t1.status
                FROM trades t1
                JOIN (
                    SELECT position_id, MAX(timestamp) AS max_ts
                    FROM trades
                    WHERE event_type IN (?, ?, ?, ?)
                      AND position_id IS NOT NULL
                      AND position_id != ''
                      AND position_id != 'ALERT'
                    GROUP BY position_id
                ) t2
                  ON t1.position_id = t2.position_id
                 AND t1.timestamp = t2.max_ts
            """,
                lifecycle_events,
            )

            return sum(
                1
                for row in cursor.fetchall()
                if row["status"] == PositionStatus.OPENED.value
            )

    @staticmethod
    def _parse_metadata(raw: str | None) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _parse_timestamp(raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:
            ts = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts
