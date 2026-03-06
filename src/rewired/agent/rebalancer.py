"""Universe reader — simplified rebalancer.

Reads the current state of ``universe.yaml`` directly and returns a
snapshot of every stock's L×T coordinate.  All tier/layer changes are
now performed exclusively through the Oracle JSON Gateway (GUI) or the
``universe add`` CLI command.

No Gemini calls.  No evaluation pipeline.  Pure data read.
"""

from __future__ import annotations

import logging
from typing import Any

from rewired.models.universe import (
    Layer,
    Tier,
    load_universe,
    LAYER_NAMES,
    TIER_NAMES,
)

logger = logging.getLogger(__name__)


# ── Public API ───────────────────────────────────────────────────────────


def rebalance_universe(*, dry_run: bool = False) -> list[dict[str, Any]]:
    """Return a snapshot of the current universe state.

    No automated tier changes are performed — all mutations go through
    the Oracle JSON Gateway or CLI.  The ``dry_run`` flag is accepted
    for CLI compatibility but has no effect (there is nothing to apply).

    Returns a list of stock summary dicts (one per stock).
    """
    universe = load_universe()

    result: list[dict[str, Any]] = []
    for stock in universe.stocks:
        result.append({
            "ticker": stock.ticker,
            "name": stock.name,
            "layer": f"L{stock.layer.value}",
            "tier": f"T{stock.tier.value}",
            "max_weight_pct": stock.max_weight_pct,
            "notes": stock.notes or "",
            "action": "current",
        })

    logger.info("Universe snapshot: %d stocks loaded.", len(result))
    return result


def _try_invalidate_gui_cache() -> None:
    """Attempt to invalidate the GUI state cache after universe mutation."""
    try:
        from rewired.gui.state import invalidate_universe
        invalidate_universe()
    except ImportError:
        pass  # GUI not installed or not running
    except Exception as exc:
        logger.debug("Could not invalidate GUI cache: %s", exc)
