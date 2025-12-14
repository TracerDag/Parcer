from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .exchanges.protocol import ExchangeClient

if TYPE_CHECKING:
    from .settings import Settings


@dataclass(slots=True)
class AppContainer:
    settings: "Settings"
    shutdown: asyncio.Event = field(default_factory=asyncio.Event)
    exchange_clients: dict[str, ExchangeClient] = field(default_factory=dict)


def build_container(settings: "Settings", exchange_clients: dict[str, ExchangeClient] | None = None) -> AppContainer:
    """Build application container with exchange clients."""
    clients = exchange_clients or {}
    return AppContainer(
        settings=settings,
        exchange_clients=clients
    )
