"""Portfolio tracking: snapshots and performance history."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rewired import get_data_dir
from rewired.models.portfolio import Portfolio


def _snapshots_path() -> Path:
    """Return the snapshots file path."""
    return get_data_dir() / "snapshots.json"


def snapshot_portfolio(portfolio: Portfolio) -> None:
    """Save a point-in-time snapshot of portfolio for historical tracking."""
    path = _snapshots_path()

    snapshots = []
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                snapshots = json.load(f)
        except (json.JSONDecodeError, OSError):
            snapshots = []

    snapshot = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_value_eur": portfolio.total_value_eur,
        "cash_eur": portfolio.cash_eur,
        "invested_eur": portfolio.invested_eur,
        "num_positions": len(portfolio.positions),
        "positions": {
            t: {"shares": p.shares, "value_eur": p.market_value_eur, "pnl_eur": p.unrealized_pnl_eur}
            for t, p in portfolio.positions.items()
        },
    }
    snapshots.append(snapshot)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, indent=2)
