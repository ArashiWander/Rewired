# Rewired Index

Rewired Index is a Python CLI (with optional web dashboard) for monitoring AI-era market signals and translating them into portfolio sizing guidance.

It combines three signal categories:
- **Macro** (30%)
- **Sentiment** (30%)
- **AI Health** (40%)

The composite engine uses a **worst-of override**: if any category is `RED`, the overall signal cannot be better than `ORANGE`.

## Features

- Compute live market signals from FRED, Yahoo Finance, and optional Gemini analysis
- Keep append-only signal color history in `data/signal_history.json`
- Track portfolio positions and transactions in JSON state
- Generate allocation suggestions and Trading 212 Pie target weights
- Dispatch alerts to console and optional Telegram channel
- Run a scheduler for periodic checks and summaries
- Launch an optional NiceGUI dashboard

## Project Structure

```text
config/                   # Static YAML config (signals, universe, portfolio, notifications)
data/                     # Runtime JSON state (portfolio, signal history, snapshots, cache)
src/rewired/
  data/                   # External data fetchers (yfinance, FRED, Gemini CAPEX helpers)
  signals/                # Category signal calculators + composite aggregation
  portfolio/              # Portfolio state, sizing, tracking logic
  agent/                  # Gemini-powered analyst/regime assessment
  notifications/          # Console + Telegram dispatching
  gui/                    # NiceGUI dashboard (optional dependency)
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

# with everything
pip install -e ".[dev,gui]"
```

## Environment Variables

Create a `.env` file in the repository root:

```env
FRED_API_KEY=your_fred_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.1-pro
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

### Which keys are needed?

- `FRED_API_KEY`: macro data quality improves with FRED access
- `GEMINI_API_KEY`: required for `rewired analyze` and `rewired regime`
- `GEMINI_MODEL` (optional): manually pin a specific Gemini model; if omitted, the app auto-selects the strongest available Pro model
- `TELEGRAM_*`: required only for Telegram notifications

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

Run scheduler (foreground):

```bash
rewired monitor
```

Launch web dashboard (if `nicegui` installed):

```bash
rewired gui --port 8080
```

## CLI Commands

- `rewired signals` — compute and print current macro/sentiment/AI-health signals
- `rewired universe` — show configured LxT universe matrix
- `rewired portfolio` — show portfolio, refresh prices when positions exist
- `rewired portfolio add` — record BUY/SELL transaction
- `rewired suggest` — generate signal-aware sizing suggestions
- `rewired pies` — show Trading 212 Pie target allocation table
- `rewired analyze` — run Gemini portfolio + signal analysis
- `rewired regime` — run Gemini market regime assessment
- `rewired gui` — start NiceGUI dashboard
- `rewired monitor` — run periodic monitor loop
- `rewired history` — display signal color change history

Every CLI command has a corresponding feature in the web dashboard (see below).

## Web Dashboard

Launch with `rewired gui --port 8080`. The dashboard provides full feature parity with the CLI across five tabs:

| Tab | Features | CLI equivalent |
|-----|----------|----------------|
| **Actions** | Pies allocation table, sizing suggestions, decision logic explainer, action playbook | `rewired pies`, `rewired suggest` |
| **Signals** | Traffic-light board, per-metric drill-down, scoring explainer, color-change history | `rewired signals`, `rewired history` |
| **Portfolio** | Positions table, trade recording form, transaction history, universe matrix | `rewired portfolio`, `rewired portfolio add`, `rewired universe` |
| **Analysis** | On-demand Gemini narrative analysis, regime assessment with confidence/risk | `rewired analyze`, `rewired regime` |
| **Monitor** | Start/stop background signal monitor, run-once button, schedule display, data export (JSON/CSV) | `rewired monitor` |

Each tab includes contextual guidance explaining how conclusions are calculated and what steps to take next.

## Data & State

Runtime state is persisted under `data/`:

- `portfolio.json` — positions, transactions, cash, totals
- `signal_history.json` — append-only signal color transitions
- `capex_cache.json` — cached CAPEX-related AI health data

Configuration lives under `config/` and is loaded from YAML on demand.

## Signal Logic

Scoring model:

- `green=1.0`, `yellow=2.0`, `orange=3.0`, `red=4.0`
- Weighted category average is mapped back to a color
- Thresholds: `<=1.5 green`, `<=2.5 yellow`, `<=3.5 orange`, `>3.5 red`

Composite constraints:

- Weights: macro `0.30`, sentiment `0.30`, AI health `0.40`
- Worst-of override: any `RED` category floors overall signal at `ORANGE`

## Portfolio Sizing Model

Portfolio rules are driven by `config/portfolio.yaml`:

- Tier base allocation: `T1=40%`, `T2=30%`, `T3=20%`, `T4=10%`
- Signal multipliers: `green=1.0`, `yellow=0.7`, `orange=0.4`, `red=0.1`
- Tier actions by signal color (hold/trim/exit)
- Constraints include max single position %, min position size in EUR, and max positions

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
pip install -e ".[dev,gui]"
```

There is a `tests/` package scaffold with `pytest` in dev dependencies, but no full test suite yet.

## Notes

- This tool is for research and process discipline, not financial advice.
- API providers and ticker availability can change over time.
- Keep config and universe files under version control; treat `data/` as runtime state.
