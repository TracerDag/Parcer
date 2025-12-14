"""Position tracking for arbitrage strategies."""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone


class PositionStatus(Enum):
    """Position lifecycle status."""

    PENDING = "pending"
    OPENED = "opened"
    CLOSING = "closing"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class Position:
    """Represents an arbitrage position (pair of legs)."""

    position_id: str
    symbol_a: str
    exchange_a: str
    symbol_b: str
    exchange_b: str
    scenario: str
    leg_a_side: str
    leg_a_quantity: float
    leg_b_side: str
    leg_b_quantity: float
    entry_price_a: float = 0.0
    entry_price_b: float = 0.0
    entry_spread: float = 0.0
    status: PositionStatus = PositionStatus.PENDING
    leg_a_order_id: str | None = None
    leg_b_order_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    exit_spread: float | None = None
    pnl: float | None = None

    @property
    def is_open(self) -> bool:
        return self.status == PositionStatus.OPENED

    @property
    def is_closed(self) -> bool:
        return self.status == PositionStatus.CLOSED

    def mark_opened(self, entry_price_a: float, entry_price_b: float) -> None:
        self.status = PositionStatus.OPENED
        self.entry_price_a = entry_price_a
        self.entry_price_b = entry_price_b
        self.entry_spread = self._calculate_spread(entry_price_a, entry_price_b)
        self.opened_at = datetime.now(timezone.utc)

    def mark_closed(self, exit_price_a: float, exit_price_b: float) -> None:
        self.status = PositionStatus.CLOSED
        self.exit_spread = self._calculate_spread(exit_price_a, exit_price_b)
        self.closed_at = datetime.now(timezone.utc)
        self._calculate_pnl(exit_price_a, exit_price_b)

    def mark_error(self) -> None:
        self.status = PositionStatus.ERROR

    def _calculate_spread(self, price_a: float, price_b: float) -> float:
        if price_b == 0:
            return 0.0
        if self.scenario == "a":
            return (price_a - price_b) / price_b
        else:
            return (price_b - price_a) / price_a

    def _calculate_pnl(self, exit_price_a: float, exit_price_b: float) -> None:
        if self.scenario == "a":
            leg_a_pnl = (self.entry_price_a - exit_price_a) * self.leg_a_quantity
            leg_b_pnl = (exit_price_b - self.entry_price_b) * self.leg_b_quantity
        else:
            leg_a_pnl = (exit_price_a - self.entry_price_a) * self.leg_a_quantity
            leg_b_pnl = (self.entry_price_b - exit_price_b) * self.leg_b_quantity

        self.pnl = leg_a_pnl + leg_b_pnl
