# Rewired Index - AI Coding Instructions

## Architecture

Investment signal framework: external data → signal computation → portfolio sizing → output (CLI/GUI).

```
data/*.py (yfinance, FRED, Gemini)
  → signals/*.py (macro 30%, sentiment 30%, AI health 40%)
    → signals/composite.py (weighted average + worst-of override)
      → portfolio/sizing.py (4-phase: take-profit → signal exits → buys → redistribute)
        → notifications/console.py (Rich) | gui/components.py (NiceGUI)
```

**Key architectural rule**: Signals flow one direction. Data fetchers never import from signals/portfolio. The composite engine uses a worst-of override: if any category is RED, the overall signal cannot be better than ORANGE.

## Project Layout

- `config/*.yaml` — static configuration (universe, signal thresholds, allocation rules, notifications)
- `data/` — runtime JSON state (portfolio, signal history, snapshots, CAPEX cache). Created by `get_data_dir()` in `__init__.py`
- `src/rewired/models/` — Pydantic BaseModels (`SignalColor`, `SignalReading`, `Portfolio`, `Universe`)
- `src/rewired/data/` — API fetchers (yfinance, FRED, Gemini CAPEX)
- `src/rewired/signals/` — signal calculators + composite engine
- `src/rewired/portfolio/` — position management, sizing, snapshots
- `src/rewired/agent/` — Gemini LLM integration (analyst prompts, regime assessment)
- `src/rewired/gui/` — NiceGUI dashboard (optional dependency)

## Critical Conventions

**All files must use** `from __future__ import annotations` and explicit `encoding="utf-8"` on every `open()` call. Windows GBK encoding breaks otherwise.

**Never use the `€` symbol** in output strings. Use the `EUR` text constant from `console.py` instead:
```python
EUR = "EUR"  # notifications/console.py:13
console.print(f"{value:.2f} {EUR}")
```

**Lazy imports in CLI commands** — heavy modules (Gemini, NiceGUI, yfinance) are imported inside function bodies, not at module top, to keep `rewired --help` fast:
```python
@main.command()
def signals():
    from rewired.signals.engine import compute_signals  # lazy
    result = compute_signals()
```

**Error handling pattern**: data fetchers catch broad `Exception`, return empty lists or safe defaults (YELLOW signal). Never let API failures crash the system.

## Data Models

All domain objects are **Pydantic BaseModel**. Enums use `str, Enum` for JSON serialization:
```python
class SignalColor(str, Enum):
    GREEN = "green"    # score 1.0
    YELLOW = "yellow"  # score 2.0
    ORANGE = "orange"  # score 3.0
    RED = "red"        # score 4.0
```

Scoring: `SIGNAL_SCORES` dict maps colors to floats. `score_to_color()` converts back. Thresholds: ≤1.5=GREEN, ≤2.5=YELLOW, ≤3.5=ORANGE, >3.5=RED.

## Configuration

YAML configs are loaded fresh each call (not cached). Portfolio allocation rules live in `config/portfolio.yaml`: tier allocations, signal multipliers, tier rules by signal color, and constraints (max 15% single position, min 10 EUR, max 15 positions).

Environment variables (`.env`): `FRED_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Each module calls `load_dotenv()` independently and checks for placeholder values like `"your_*_here"`.

## State Persistence

All runtime state is JSON in the `data/` directory. Use `get_data_dir()` (creates dir if missing). Portfolio uses `Portfolio.model_dump_json()` / `Portfolio.model_validate()`. Signal history is append-only (only logs on color change).

## Adding a New Signal Source

1. Create `src/rewired/data/new_source.py` with a function returning `list[SignalReading]`
2. Create `src/rewired/signals/new_signal.py` returning `CategorySignal`
3. Add the category to `SignalCategory` enum in `models/signals.py`
4. Wire it into `signals/engine.py:compute_signals()` and add weight in `composite.py:CATEGORY_WEIGHTS`

## Adding a New CLI Command

Add to `src/rewired/cli.py` using the `@main.command()` decorator. Use lazy imports inside the function body. Follow existing pattern: fetch data → compute → display via `notifications/console.py`.

## GUI Pattern

NiceGUI is an optional dependency (`pip install -e ".[gui]"`). The dashboard uses `gui/state.py` (TTL-cached data fetching singleton) and `gui/components.py` (card-based UI builders). Blocking API calls must use `await _run_in_thread(fn)` to keep the UI responsive.

## Developer Commands

```bash
pip install -e ".[dev,gui]"   # Install with all extras
rewired --help                 # List all 10 CLI commands
rewired signals                # Live signal check (hits yfinance/FRED/Gemini)
rewired pies                   # T212 Pies allocation table
rewired gui --port 8080        # Launch web dashboard
```

No tests exist yet. Test infrastructure is pytest (`tests/` directory, `dev` dependency group).
