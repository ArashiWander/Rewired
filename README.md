# Rewired Index

Rewired Index is a Python CLI (with optional web dashboard) for monitoring AI-era market signals and translating them into portfolio sizing guidance.

It combines three signal categories:
- **Macro** (30%)
- **Sentiment** (30%)
- **AI Health** (40%) — holds **absolute veto power** (RED → global RED)

The composite engine uses a **worst-of override**: if any category is `RED`, the overall signal cannot be better than `ORANGE`.

## Features

- Compute live market signals from FRED, Yahoo Finance, FMP, and Gemini CAPEX analysis
- Keep append-only signal color history in `data/signal_history.json`
- Track portfolio positions and transactions in JSON state
- Generate allocation suggestions and Trading 212 Pie target weights
- **Automated asset onboarding**: ticker → FMP hydration → Gemini classification → universe persistence
- **Per-company evaluation**: Gemini-powered fundamental/AI-relevance scoring (single or batch)
- **Out-of-universe evaluation**: evaluate any ticker without adding it to the portfolio
- **Ticker resolution**: free-text company names → tickers via exact/alias/fuzzy/FMP search
- **Broker integration**: IBKR adapter for live order execution (optional `[broker]` dependency)
- **DAG pipeline**: data fetch → signals → sizing → execution in a single command
- Dispatch alerts to console and optional Telegram channel
- Run a scheduler for periodic checks and summaries
- Launch an optional NiceGUI dashboard with i18n (EN/ZH)

## Project Structure

```text
config/                   # Static YAML config (signals, universe, portfolio, notifications)
data/                     # Runtime JSON state (portfolio, signal history, snapshots, cache)
src/rewired/
  data/                   # External data fetchers (yfinance, FRED, FMP, Gemini CAPEX, EDGAR, fx)
    fmp.py                # Financial Modeling Prep API wrapper (profiles, financials, CAPEX)
    ticker_resolver.py    # Free-text → ticker resolution (exact/alias/fuzzy/FMP)
  signals/                # Boolean rules engine + category signal calculators + composite
    rules.py              # Deterministic IF-THEN boolean logic trees per dimension
    composite.py          # Weighted aggregation with worst-of override
  portfolio/              # Portfolio state, sizing, tracking logic
  agent/                  # Gemini-powered analysis and evaluation
    prompts.py            # Centralized prompt registry (UPPER_SNAKE_CASE templates)
    evaluator.py          # Per-company Gemini evaluator (single + batch with throttling)
    analyst.py            # Portfolio/signal/regime analysis
    gemini.py             # Gemini client wrapper (temp=0, JSON mode, retry)
  broker/                 # Broker adapters (optional)
    ibkr.py               # Interactive Brokers adapter via ib_insync
  notifications/          # Console + Telegram dispatching
  models/                 # Pydantic BaseModels
    signals.py            # SignalColor, SignalReading, SignalCategory
    portfolio.py          # Portfolio, Position, Transaction
    universe.py           # Layer, Tier, Stock, Universe + onboard_ticker()
    evaluation.py         # CompanyEvaluation, EvaluationBatch
  gui/                    # NiceGUI dashboard (optional dependency)
    app.py                # Dashboard layout with lifecycle guards
    components.py         # Card-based UI builders
    i18n.py               # Dual-language translation (EN/ZH)
    state.py              # TTL-cached data singleton
  cli.py                  # `rewired` command entrypoint
```

## Requirements

- Python `3.11+`
- Internet access for market/macro APIs
- Optional API keys depending on the commands you use

## Installation

```bash
# from project root
pip install -e .

# with development tools
pip install -e ".[dev]"

# with dashboard support
pip install -e ".[gui]"

# with broker integration
pip install -e ".[broker]"

# with everything
pip install -e ".[dev,gui,broker]"
```

## Environment Variables

Create a `.env` file in the repository root:

```env
FRED_API_KEY=your_fred_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
FMP_API_KEY=your_fmp_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

### Which keys are needed?

| Key | Required for | Fallback |
|-----|-------------|----------|
| `FRED_API_KEY` | Macro signal data quality | Safe defaults |
| `GEMINI_API_KEY` | `analyze`, `regime`, `evaluate`, `universe add` (classification) | Commands unavailable |
| `GEMINI_MODEL` | Pin a specific Gemini model (optional) | Defaults to `gemini-2.5-flash` → `gemini-2.5-pro` → `gemini-2.0-flash` |
| `FMP_API_KEY` | Company profiles, financials, CAPEX history, ticker search | Reduced data quality |
| `TELEGRAM_*` | Telegram notifications | Console only |

If keys are missing, most data fetchers fail safely and return defensive defaults instead of crashing.

## Quick Start

```bash
rewired --help
rewired signals
rewired universe
rewired portfolio
rewired suggest
rewired pies
```

Record a trade:

```bash
rewired portfolio add --ticker NVDA --action BUY --shares 1.5 --price 120.0 --notes "Initial position"
```

Add a new asset to the universe (auto-classified by Gemini):

```bash
rewired universe add PLTR
# → FMP profile fetched → Gemini classifies → Layer: L2, Tier: T2, MaxWeight: 8%
rewired universe add appl
# → Input normalized (e.g., APPL/appl -> AAPL) before hydration/classification
```

Evaluate a company:

```bash
rewired evaluate -t NVDA          # Single stock
rewired evaluate -t APPL          # Typo/case input auto-resolves via resolver + FMP search
rewired evaluate --all            # Full universe (batched with rate limiting)
```

Resolve a company name to ticker:

```bash
rewired resolve "nvidia"          # → NVDA (exact match)
rewired resolve "palantir"        # → PLTR (fuzzy/FMP search)
```

Run full pipeline (data → signals → sizing → execution):

```bash
rewired pipeline                  # Dry run by default
rewired pipeline --execute        # Live execution via IBKR
```

Launch web dashboard:

```bash
rewired gui --port 8080
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `rewired signals` | Compute and print current macro/sentiment/AI-health signals |
| `rewired universe` | Show configured LxT universe matrix |
| `rewired universe add <TICKER>` | Onboard a new asset (FMP hydration → Gemini classification → save) |
| `rewired portfolio` | Show portfolio, refresh prices when positions exist |
| `rewired portfolio add` | Record BUY/SELL transaction |
| `rewired suggest` | Generate signal-aware sizing suggestions |
| `rewired pies` | Show Trading 212 Pie target allocation table |
| `rewired analyze` | Run Gemini portfolio + signal analysis (Markdown tables) |
| `rewired regime` | Run Gemini market regime assessment |
| `rewired evaluate` | Per-company Gemini evaluation (single `-t TICKER` or `--all`) |
| `rewired resolve <NAME>` | Resolve free-text company name to ticker symbol |
| `rewired execute` | Execute pending sizing orders via IBKR broker |
| `rewired pipeline` | Run full DAG: data → signals → sizing → (optional) execution |
| `rewired gui` | Start NiceGUI dashboard |
| `rewired monitor` | Run periodic signal monitor loop |
| `rewired history` | Display signal color change history |
| `rewired doctor` | Diagnose Gemini API: list available models, test fallback chain |

Every CLI command has a corresponding feature in the web dashboard.

## Web Dashboard

Launch with `rewired gui --port 8080`. The dashboard provides full feature parity with the CLI across six tabs:

| Tab | Features | CLI equivalent |
|-----|----------|----------------|
| **Actions** | Pies allocation table, sizing suggestions, decision logic explainer, action playbook | `pies`, `suggest` |
| **Signals** | Traffic-light board, per-metric drill-down, scoring explainer, color-change history | `signals`, `history` |
| **Portfolio** | Positions table, trade recording, transaction history, universe matrix, universe onboarding card | `portfolio`, `portfolio add`, `universe`, `universe add` |
| **Analysis** | On-demand Gemini narrative analysis, regime assessment with confidence/risk | `analyze`, `regime` |
| **Evaluation** | Single-stock or full-universe Gemini evaluation with scores, catalysts, risks | `evaluate` |
| **Monitor** | Start/stop background signal monitor, run-once button, schedule display, data export (JSON/CSV) | `monitor` |

The dashboard supports **EN/ZH language switching** and uses **safe lifecycle guards** (`_safe_clear`, `on_disconnect` timer cleanup) to prevent errors when clients disconnect.

## Data & State

Runtime state is persisted under `data/`:

- `portfolio.json` — positions, transactions, cash, totals
- `signal_history.json` — append-only signal color transitions
- `capex_cache.json` — cached CAPEX-related AI health data

Configuration lives under `config/` and is loaded from YAML on demand.

## Signal Logic

Scoring model (higher = better):

| Color | Score |
|-------|-------|
| GREEN | 4.0 |
| YELLOW | 3.0 |
| ORANGE | 2.0 |
| RED | 1.0 |

Score → color mapping: `>=3.5 GREEN`, `>=2.5 YELLOW`, `>=1.5 ORANGE`, `<1.5 RED`

Composite constraints:

- Weights: Macro `0.30`, Sentiment `0.30`, AI Health `0.40`
- **Worst-of override**: any `RED` category floors the overall signal at `ORANGE`
- **AI Health veto**: if AI Health = RED, global signal = RED regardless of other categories

Signal evaluation uses **deterministic boolean rules** (not averaged sub-metrics):

- **Macro**: PMI + PCE + Unemployment + Yield Curve + Retail Sales
- **Sentiment**: VIX level, contango/backwardation, moving average regime
- **AI Health**: Big 4 CAPEX trajectory via Gemini grounded search

## Universe & Onboarding

Assets are organized in a Layer × Tier matrix:

| Layer | Description | Examples |
|-------|-------------|---------|
| L1 | Core AI infrastructure | NVDA, TSM |
| L2 | AI platform / cloud | MSFT, GOOGL, AMZN |
| L3 | AI-integrated software | CRM, NOW, ADBE |
| L4 | AI-adjacent / picks & shovels | ANET, MRVL |
| L5 | Broader tech / enablers | AAPL, ASML |

Tiers (T1-T4) set maximum portfolio weight constraints.

**Automated onboarding** (`rewired universe add <TICKER>`):
1. FMP profile hydration (name, sector, industry, market cap)
2. Gemini classification (layer/tier/max weight with confidence score)
3. Universe persistence (appended to `config/universe.yaml`)

Fallback if Gemini unavailable: Layer L4, Tier T3, MaxWeight 5%.

## Portfolio Sizing Model

Portfolio rules are driven by `config/portfolio.yaml`:

- Tier base allocation: `T1=40%`, `T2=30%`, `T3=20%`, `T4=10%`
- Signal multipliers: `green=1.0`, `yellow=0.7`, `orange=0.4`, `red=0.1`
- Tier actions by signal color (hold/trim/exit)
- Constraints include max single position %, min position size in EUR, and max positions

## Broker Integration

Optional IBKR integration (`pip install -e ".[broker]"`):

- `IBKRBroker` adapter wraps `ib_insync` for live order execution
- Supports market/limit orders, batch execution, position queries
- GUI execute modal with order preview table and confirmation
- Pipeline command chains: data → signals → sizing → IBKR execution

## Gemini Integration

All Gemini calls use `temperature=0.0` for deterministic output. Structured responses use `json_output=True` with `response_mime_type="application/json"`. Auto-retry (max 2) on malformed JSON.

**Prompt registry** (`agent/prompts.py`) enforces:
- **Markdown table output** on analysis prompts (PORTFOLIO_ANALYSIS, SIGNAL_ANALYSIS, STOCK_ANALYSIS)
- **Strict JSON output** on classification/evaluation prompts
- Naming convention: `{DOMAIN}_{ACTION}` in UPPER_SNAKE_CASE

**Batch evaluation** uses `ThreadPoolExecutor(max_workers=5)` with 2-second sleep between chunks to respect API rate limits.

## Scheduling & Notifications

`rewired monitor` currently schedules:

- signal checks every 4 hours
- daily portfolio summary at `18:30`
- weekly summary on Monday at `08:00`

Notification routing:

- console output is always active
- Telegram is used only when bot token + chat ID are configured

## Development

```bash
pip install -e ".[dev,gui,broker]"
pytest tests/ -v
```

Test infrastructure uses `pytest` with the `tests/` package.

## Notes

- This tool is for research and process discipline, not financial advice.
- API providers and ticker availability can change over time.
- Keep config and universe files under version control; treat `data/` as runtime state.
