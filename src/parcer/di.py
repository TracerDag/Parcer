from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .settings import Settings


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    shutdown: asyncio.Event = field(default_factory=asyncio.Event)


def build_container(settings: Settings) -> AppContainer:
    return AppContainer(settings=settings)
