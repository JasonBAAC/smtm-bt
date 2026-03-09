# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Install dependencies
```bash
pip install -r requirements-dev.txt
```

### Run all unit tests
```bash
coverage run --omit="*/test*" -m pytest ./tests/unit_tests
# or
python -m unittest discover ./tests *test.py -v
```

### Run a single test file
```bash
python -m pytest tests/unit_tests/strategy_sma_0_test.py -v
```

### Run integration tests (requires real exchange access)
```bash
python -m unittest discover ./tests/integration_tests *ITG_test.py -v
```

### Run the system
```bash
# Interactive simulator
python -m smtm --mode 0

# Single simulation
python -m smtm --mode 1 --budget 50000 --from_dash_to 201220.170000-201221 --term 60 --strategy SMA --currency BTC

# Real trading (interactive CLI)
python -m smtm --mode 2 --budget 50000 --term 60 --strategy BNH --currency ETH

# Telegram chatbot trading
python -m smtm --mode 3 --token <token> --chatid <chatid>

# Mass simulation from config file
python -m smtm --mode 4 --config generated_config.json

# Generate config files for mass simulation
python -m smtm --mode 5 --budget 50000 --title SMA_6H_week --strategy SMA --currency ETH --from_dash_to 210804.000000-210811.000000 --offset 360 --file generated_config.json
```

## Architecture

**Layered Architecture:**

| Layer | Modules | Role |
|---|---|---|
| Controller | `Simulator`, `Controller`, `TelegramController`, `MassSimulator` | User Interface / CLI |
| Operator | `Operator`, `SimulationOperator` | Orchestration & Trading Loop |
| Core | `DataProvider`, `Strategy`, `Trader`, `Analyzer` | Core Trading Logic |

**Core trading loop** (driven by `Operator._execute_trading`):
1. `DataProvider.get_info()` → fetch OHLCV candle data
2. `Strategy.update_trading_info(info)` → update strategy state
3. `Strategy.get_request()` → generate buy/sell/cancel orders
4. `Trader.send_request(requests, callback)` → execute orders
5. `Strategy.update_result(result)` → reflect results back

The `Worker` class runs the loop in a background daemon thread via a thread-safe queue.

### Key Module Groups

**`smtm/data/`** — Data providers
- `DataProvider` (abstract): defines `get_info()` interface returning OHLCV dicts with `type: "primary_candle"`
- `UpbitDataProvider`, `BithumbDataProvider`, `BinanceDataProvider`: live exchange REST APIs
- `SimulationDataProvider`: replays historical data from `DataRepository`
- `DataRepository`: caches exchange data in a local SQLite DB (`smtm.db`), fetching from API if not cached

**`smtm/strategy/`** — Trading strategies
- `Strategy` (abstract): defines `initialize`, `get_request`, `update_trading_info`, `update_result`
- `StrategyFactory`: creates strategy instances by `CODE` string (BNH, SMA, RSI, SML, DML, SAS, HEY)
- `StrategySma0` (CODE=`SMA`): Golden/Dead Cross on SHORT/MID/LONG moving averages with split trading (`STEP`)
- `StrategySmaMl` (CODE=`SML`): SMA strategy augmented with `sklearn` `LinearRegression` for slope prediction

**`smtm/trader/`** — Order execution
- `Trader` (abstract): defines `send_request`, `cancel_request`, `cancel_all_requests`, `get_account_info`
- `UpbitTrader`, `BithumbTrader`: real exchange APIs using JWT auth
- `SimulationTrader` + `VirtualMarket`: simulates order fills based on High/Low prices of historical candles
- `DemoTrader`: fake trader for dry-run testing

**`smtm/controller/`** — User interfaces
- `Simulator`: interactive CLI for running simulations
- `Controller`: interactive CLI for live trading
- `TelegramController`: controls trading via Telegram bot commands
- `MassSimulator`: runs many simulations in parallel via `multiprocessing`

**Support modules**
- `Config` (`config.py`): global settings — `simulation_source`, `candle_interval`, `operation_log_level`, language (`SMTM_LANG` env var)
- `LogManager`: `RotatingFileHandler`-based logging
- `DateConverter`: converts between ISO8601, timestamps, and the system's `YYMMDD.HHMMSS` date format
- `Analyzer`: records all trades and generates `mplfinance` OHLC charts with buy/sell markers and yield curves

### Adding a New Strategy
1. Create `smtm/strategy/strategy_<name>.py` subclassing `Strategy`
2. Set unique `CODE` and `NAME` class attributes
3. Register in `StrategyFactory.STRATEGY_LIST` in `smtm/strategy/strategy_factory.py`
4. Add corresponding unit test in `tests/unit_tests/strategy_<name>_test.py`

### Configuration
- Exchange API keys go in a `.env` file (loaded via `python-dotenv`)
- For Telegram mode, pass `--token` and `--chatid` as CLI args or set them in `TelegramController`
- `Config.simulation_source` controls whether simulations use Upbit or Binance historical data
