from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .settings import Settings


def _deep_set(obj: dict[str, Any], path: list[str], value: Any) -> None:
    cur: dict[str, Any] = obj
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[path[-1]] = value


def _parse_env_value(raw: str) -> Any:
    try:
        return yaml.safe_load(raw)
    except Exception:
        return raw


def _apply_env_overrides(data: dict[str, Any], *, prefix: str = "PARCER_") -> dict[str, Any]:
    merged: dict[str, Any] = dict(data)

    for key, raw_value in os.environ.items():
        if not key.startswith(prefix):
            continue

        remainder = key[len(prefix) :]
        if remainder in {"CONFIG", "LOG_LEVEL"}:
            continue

        path = [p.lower() for p in remainder.split("__") if p]
        if not path:
            continue

        _deep_set(merged, path, _parse_env_value(raw_value))

    return merged


def load_settings(config_path: str | Path | None = None) -> Settings:
    if config_path is None:
        config_path = os.environ.get("PARCER_CONFIG", "config.yml")

    path = Path(config_path)
    if path.exists():
        raw = path.read_text(encoding="utf-8")
        loaded = yaml.safe_load(raw)
        if loaded is None:
            data: dict[str, Any] = {}
        elif isinstance(loaded, dict):
            data = loaded
        else:
            raise ValueError(f"Config root must be a mapping, got: {type(loaded)!r}")
    else:
        data = {}

    data = _apply_env_overrides(data)

    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration: {exc}") from exc
