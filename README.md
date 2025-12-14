# parcer

Minimal bootstrap scaffold for the `parcer` arbitrage bot.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Configuration

Configuration is loaded from YAML (default: `config.yml`) and then overridden by environment variables.

- Default config path: `config.yml`
- Override config path with: `PARCER_CONFIG=/path/to/config.yml`
- Environment overrides prefix: `PARCER_`
- Nested keys use `__` (double underscore)

Example `config.yml` (see `config.example.yml`):

```yaml
env: dev
proxy:
  enabled: false
  url: "http://127.0.0.1:8080"
  username: null
  password: null

trading:
  leverage: 2
  max_positions: 3
  fixed_order_size: 25.0

exchanges:
  binance:
    enabled: true
    sandbox: false
    credentials:
      api_key: "..."
      api_secret: "..."
    options:
      recv_window_ms: 5000
```

Environment override examples:

```bash
export PARCER_TRADING__LEVERAGE=5
export PARCER_EXCHANGES__BINANCE__SANDBOX=true
```

## Run

```bash
python -m parcer --config config.yml
```

If the config file does not exist, `parcer` will start with defaults (useful for verifying installation).
