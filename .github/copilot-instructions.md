# Rewired Index - AI Coding Instructions

## Architecture

Agentic Decision System: external data → boolean rules engine → composite signal → portfolio sizing → output (CLI/GUI).

**Core Principle: Cold Determinism.** The AI Agent has ZERO autonomous investment authority. It is strictly an NLP-capable structured data extractor. All decisions flow through predefined boolean logic trees. If data is missing, the system halts (circuit breaker) or defaults to defensive (ORANGE).

```
data/*.py (yfinance, FRED, Gemini+EDGAR)
  → signals/rules.py (boolean IF-THEN logic trees per dimension)
    → signals/*_signal.py (macro, sentiment, ai_health calculators)
      → signals/composite.py (weighted: Macro 30%, Sentiment 30%, AI Health 40% + AI veto)
        → portfolio/sizing.py (4-phase: take-profit → signal exits → buys → redistribute)
          → notifications/console.py (Rich) | gui/components.py (NiceGUI)
```

**Key architectural rules**:
- Signals flow one direction. Data fetchers never import from signals/portfolio.
- AI Health holds **absolute veto power**: if AI_HEALTH = RED, global signal = RED regardless.
- Any other category RED: composite floor = ORANGE (worst-of override).
- Signal evaluation is deterministic boolean rules, NOT averaged sub-metric scores.

## Project Layout

- `config/*.yaml` — static configuration (universe, signal **rules** and thresholds, allocation rules, notifications)
- `data/` — runtime JSON state (portfolio, signal history, snapshots, CAPEX cache). Created by `get_data_dir()` in `__init__.py`
- `src/rewired/models/` — Pydantic BaseModels (`SignalColor`, `SignalReading`, `Portfolio`, `Universe`, `CircuitBreakerError`, `DataQuality`, `CompanyEvaluation`, `EvaluationBatch`)
- `src/rewired/data/` — API fetchers (yfinance, FRED, FMP, Gemini CAPEX, SEC EDGAR, ticker resolver)
- `src/rewired/signals/` — boolean rules engine (`rules.py`) + signal calculators + composite engine
- `src/rewired/portfolio/` — position management, sizing, snapshots
- `src/rewired/agent/` — Gemini LLM integration (strict confinement: temp=0, JSON mode, retry), centralized prompts (`prompts.py`), per-company evaluator (`evaluator.py`)
- `src/rewired/gui/` — NiceGUI dashboard (optional dependency)

## Build And Test

Use the project virtualenv when present. Canonical install, test, and run commands come from `pyproject.toml`, `cli.py`, and the existing pytest suite:

```bash
pip install -e .
pip install -e ".[dev]"
pip install -e ".[gui]"
pip install -e ".[dev,gui,broker]"
pytest tests/ -v
rewired --help
rewired signals
rewired gui --port 8080
```

Prefer targeted regression checks around the subsystem you changed before running the full suite:

```bash
pytest tests/test_composite.py -v
pytest tests/test_ai_health.py tests/test_fmp.py tests/test_gemini.py -v
pytest tests/test_gui_app.py tests/test_prices.py -v
```

If you touch optional GUI code, install `.[gui]` first. If you touch broker execution paths, install `.[broker]` or `.[dev,gui,broker]`.

## Critical Conventions

**For new or edited Python modules**, prefer `from __future__ import annotations`. For any file I/O you add or modify, always pass `encoding="utf-8"` to `open()`. Windows GBK defaults break otherwise.

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

**Error handling pattern**: data fetchers catch broad `Exception`, return empty lists or safe defaults. Missing critical data triggers circuit breaker (defaults to ORANGE). Never let API failures crash the system.

**Pattern anchors**:
- `src/rewired/cli.py` — lazy-import CLI style and command inventory
- `src/rewired/signals/composite.py` — canonical weighting and override logic
- `src/rewired/data/ai_health.py` — CAPEX cache/schema handling and Gemini edge cases
- `src/rewired/gui/state.py` — GUI cache plus non-blocking lock pattern
- `src/rewired/gui/app.py` — NiceGUI render lifecycle constraints and Windows exception filtering

## Scoring Convention (Blueprint)

Higher scores = better conditions:
```python
class SignalColor(str, Enum):
    GREEN = "green"    # score 4.0 (best)
    YELLOW = "yellow"  # score 3.0
    ORANGE = "orange"  # score 2.0
    RED = "red"        # score 1.0 (worst)
```

`SIGNAL_SCORES` maps colors to floats. `score_to_color()` converts back: >=3.5 GREEN, >=2.5 YELLOW, >=1.5 ORANGE, <1.5 RED.

## Signal Rules Engine

Signal evaluation uses **deterministic boolean rules** in `signals/rules.py`, NOT averaged sub-metric scores. Rules are evaluated top-to-bottom (most defensive first). Config in `config/signals.yaml`.

**Macro** (3 dimensions: PMI, PCE, Unemployment + Yield Curve, Retail Sales):
- RED: PMI < 48 for 2 consecutive months AND Retail Sales MoM negative
- ORANGE: Core PCE > 0.2% MoM AND Yield Curve inverted
- YELLOW: Unemployment +0.2% MoM BUT PMI > 50
- GREEN: PMI > 50 AND PCE <= 0.2% MoM

**Sentiment** (VIX-based, contrarian):
- RED: VIX > 35 AND backwardation (VIX > VIX3M)
- ORANGE: VIX > 25 AND 5MA > 20MA
- YELLOW: VIX 18-25
- GREEN: VIX < 18 AND contango

**AI Health** (CAPEX analysis via Gemini, absolute veto):
- RED (VETO): Any Big 4 CapEx CUT → overrides everything to RED
- ORANGE: CapEx growth decelerating
- YELLOW: CapEx stable/plateau
- GREEN: CapEx accelerating

## Gemini Integration (Strict Confinement)

All Gemini calls use `temperature=0.0` for deterministic output. Set `json_output=True` for structured responses with `response_mime_type="application/json"`. Auto-retry is deliberately conservative (`max_retries=1` by default in `agent/gemini.py`) to avoid quota burn.

Important Gemini constraints:
- Do not combine `json_output=True` with `search_grounding=True`; the API rejects tool use with JSON MIME output. The wrapper now disables grounding in that case.
- Treat `429 RESOURCE_EXHAUSTED`, `504 DEADLINE_EXCEEDED`, and connection-reset errors as stop conditions, not reasons to keep cascading across models.
- CAPEX analysis in `data/ai_health.py` is FMP-first; yfinance is fallback only.
- CAPEX prompt/parser contract uses `capex_trend`; parser still accepts legacy `trend` for backward compatibility.
- If CAPEX schema or parser semantics change, bump `_CAPEX_CACHE_VERSION` or stale `data/capex_cache.json` entries will persist.

**Centralized Prompt Registry** — ALL Gemini prompt templates live in `agent/prompts.py`. Template variables use `str.format()` placeholders. Naming convention: `{DOMAIN}_{ACTION}` in UPPER_SNAKE_CASE. System instructions: `SYSTEM_ANALYST`, `SYSTEM_EVALUATOR`, `SYSTEM_REGIME`, `SYSTEM_CAPEX`.

**Per-Company Evaluator** — `agent/evaluator.py` takes a `Stock`, gathers FMP financial data, and sends through Gemini with `COMPANY_EVALUATE` prompt to produce a `CompanyEvaluation` (Pydantic model). Supports single-stock and batch-universe evaluation. Batch evaluation is intentionally throttled in small chunks and aborts remaining work early when rate-limit/timeout responses appear.

## FMP Data Pipeline

`data/fmp.py` wraps the Financial Modeling Prep API (v3). Environment variable: `FMP_API_KEY`. Provides:
- Company profiles (batch-capable)
- Income statements, balance sheets, cash flow (quarterly/annual)
- Key metrics & financial ratios
- Earnings surprises & analyst estimates
- Real-time quotes (batch-capable)
- CAPEX history helpers (`get_capex_history()`, `get_big4_capex_summary()`)
- Ticker search

All methods return empty containers on failure. Never crashes.

## Ticker Resolver

`data/ticker_resolver.py` resolves free-text company names to tickers using four strategies in priority order:
1. **Exact** — case-insensitive match against universe YAML
2. **Alias** — hardcoded alias table ("google" → GOOGL, "facebook" → META, etc.)
3. **Fuzzy** — `rapidfuzz.fuzz.token_set_ratio` against universe + aliases (threshold: 80)
4. **FMP search** — online fallback via `/search` endpoint

Returns `ResolvedTicker` dataclass with `ticker`, `name`, `score`, `source`, `in_universe`.

## Configuration

YAML configs are loaded fresh each call (not cached). Portfolio allocation rules live in `config/portfolio.yaml`: tier allocations, signal multipliers, tier rules by signal color, and constraints (max 15% single position, min 10 EUR, max 15 positions). Signal boolean rule thresholds live in `config/signals.yaml`.

Environment variables (`.env`): `FRED_API_KEY`, `GEMINI_API_KEY`, `FMP_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Each module calls `load_dotenv()` independently and checks for placeholder values like `"your_*_here"`.

## State Persistence

All runtime state is JSON in the `data/` directory. Use `get_data_dir()` (creates dir if missing). Portfolio uses `Portfolio.model_dump_json()` / `Portfolio.model_validate()`. Signal history is append-only (only logs on color change). CAPEX cache has `schema_version` field for migration.

## Adding a New Signal Source

1. Create `src/rewired/data/new_source.py` with a function returning `list[SignalReading]` (include `metadata` dict for rules engine)
2. Add boolean evaluation rules to `src/rewired/signals/rules.py`
3. Create `src/rewired/signals/new_signal.py` that calls the rules engine
4. Add the category to `SignalCategory` enum in `models/signals.py`
5. Wire it into `signals/engine.py:compute_signals()` and add weight in `composite.py:CATEGORY_WEIGHTS`

## Adding a New CLI Command

Add to `src/rewired/cli.py` using the `@main.command()` decorator. Use lazy imports inside the function body. Follow existing pattern: fetch data → compute → display via `notifications/console.py`.

## GUI Pattern

NiceGUI is an optional dependency (`pip install -e ".[gui]"`). The dashboard uses `gui/state.py` (TTL-cached data fetching singleton) and `gui/components.py` (card-based UI builders). Blocking API calls must use `await _run_in_thread(fn)` to keep the UI responsive.

Critical GUI constraints:
- In `gui/app.py`, do all async fetching before entering `with container:` blocks. Do not `await` inside a NiceGUI slot context; it can detach the active parent and blank tabs.
- Rebuild each tab independently so one rendering failure does not blank the whole dashboard.
- Use `DashboardState` getters and caches; do not trigger expensive full-universe Gemini evaluation from background refresh paths.
- `gui/state.py` uses per-source non-blocking locks to prevent duplicate fetch storms. Preserve that pattern when adding new cached sources.
- On Windows, benign Proactor transport disconnect errors are intentionally filtered in the GUI exception handler. Do not remove that suppression unless you have a verified replacement.
- For live ECharts updates, return raw JavaScript object literal strings where NiceGUI expects JS source; Python dicts can serialize incorrectly for `:setOption(...)` calls.

## Developer Commands

```bash
pip install -e ".[dev,gui,broker]"   # Install with all extras
rewired --help                 # List all CLI commands
rewired signals                # Live signal check (hits yfinance/FRED/Gemini)
rewired pies                   # T212 Pies allocation table
rewired evaluate --all         # Per-company Gemini evaluation (full universe)
rewired evaluate -t NVDA       # Single-stock evaluation
rewired resolve "nvidia"        # Ticker resolution
rewired pipeline --dry-run     # End-to-end DAG without broker execution
rewired rebalance --dry-run    # Universe tier rebalance preview
rewired gui --port 8080        # Launch web dashboard
```

Test infrastructure is pytest in `tests/`. Prefer targeted test runs for the subsystem you changed before running the full suite.
