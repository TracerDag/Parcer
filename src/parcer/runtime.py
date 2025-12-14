from __future__ import annotations

import asyncio
import logging

from .di import AppContainer

logger = logging.getLogger(__name__)


async def run(container: AppContainer) -> None:
    logger.info("runtime starting")
    logger.debug("settings=%s", container.settings.redacted())

    await asyncio.sleep(0)

    logger.info("runtime stopped")
