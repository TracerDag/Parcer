"""Exchange client initialization from settings."""

from __future__ import annotations

import logging
from typing import Dict

from .factory import create_exchange_client
from .protocol import ExchangeClient
from ..settings import Settings

logger = logging.getLogger(__name__)


def create_exchange_clients_from_settings(settings: Settings) -> Dict[str, ExchangeClient]:
    """Create exchange clients from settings configuration."""
    clients: Dict[str, ExchangeClient] = {}
    
    for exchange_name, exchange_config in settings.exchanges.items():
        if not exchange_config.enabled:
            logger.debug("Exchange %s is disabled, skipping", exchange_name)
            continue
            
        if not exchange_config.credentials:
            logger.warning("Exchange %s has no credentials configured, skipping", exchange_name)
            continue
            
        try:
            client = create_exchange_client(
                exchange=exchange_name,
                api_key=exchange_config.credentials.api_key.get_secret_value(),
                api_secret=exchange_config.credentials.api_secret.get_secret_value(),
                passphrase=exchange_config.credentials.passphrase.get_secret_value() if exchange_config.credentials.passphrase else None,
                sandbox=exchange_config.sandbox,
                **exchange_config.options,
            )
            clients[exchange_name] = client
            logger.info("Initialized exchange client for %s", exchange_name)
            
        except Exception as e:
            logger.error("Failed to initialize exchange client for %s: %s", exchange_name, e)
            continue
    
    return clients