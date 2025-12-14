from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, SecretStr


class ProxySettings(BaseModel):
    enabled: bool = False
    url: str | None = None
    username: str | None = None
    password: SecretStr | None = None

    model_config = {"extra": "forbid"}


class TradingSettings(BaseModel):
    leverage: float = Field(default=1, gt=0)
    max_positions: int = Field(default=1, ge=0)
    fixed_order_size: float = Field(default=10.0, gt=0)

    model_config = {"extra": "forbid"}


class ExchangeCredentials(BaseModel):
    api_key: SecretStr
    api_secret: SecretStr
    passphrase: SecretStr | None = None

    model_config = {"extra": "forbid"}


class ExchangeSettings(BaseModel):
    enabled: bool = True
    sandbox: bool = False
    credentials: ExchangeCredentials | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class Settings(BaseModel):
    env: str = "dev"
    proxy: ProxySettings = Field(default_factory=ProxySettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    exchanges: dict[str, ExchangeSettings] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    def redacted(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        for exch in data.get("exchanges", {}).values():
            creds = exch.get("credentials")
            if isinstance(creds, dict):
                if "api_key" in creds:
                    creds["api_key"] = "***"
                if "api_secret" in creds:
                    creds["api_secret"] = "***"
                if "passphrase" in creds and creds["passphrase"] is not None:
                    creds["passphrase"] = "***"
        proxy = data.get("proxy")
        if isinstance(proxy, dict) and proxy.get("password") is not None:
            proxy["password"] = "***"
        return data
