"""Signal computation engine — orchestrates calculators + hysteresis state machine.

The hysteresis state machine prevents whipsaw regime flips:
  - Downgrades (worse signal) are applied immediately.
  - Upgrades (better signal) require 3 consecutive days of confirmation
    before the regime actually transitions.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from rich.console import Console

from rewired import get_data_dir
from rewired.models.signals import (
    CompositeSignal,
    RegimeState,
    SignalCategory,
    SignalColor,
    _COLOR_RANK,
    color_is_better,
    color_is_worse,
)

# Inverse of _COLOR_RANK for stepping one rank at a time during upgrades.
_RANK_TO_COLOR: dict[int, SignalColor] = {v: k for k, v in _COLOR_RANK.items()}
from rewired.signals.composite import compute_composite
from rewired.signals.macro_signal import calculate_macro_signal
from rewired.signals.sentiment_signal import calculate_sentiment_signal
from rewired.signals.ai_health_signal import calculate_ai_health_signal

console = Console()
logger = logging.getLogger(__name__)

_UPGRADE_CONFIRMATION_DAYS = 3


def compute_signals() -> CompositeSignal:
    """Compute all signals and return the composite result."""
    logger.debug("Fetching macro data...")
    macro = calculate_macro_signal()

    logger.debug("Fetching sentiment data...")
    sentiment = calculate_sentiment_signal()

    logger.debug("Fetching AI health data...")
    ai_health = calculate_ai_health_signal()

    categories = {
        SignalCategory.MACRO: macro,
        SignalCategory.SENTIMENT: sentiment,
        SignalCategory.AI_HEALTH: ai_health,
    }

    raw_color, veto_active, composite_transparency = compute_composite(categories)

    # ── Apply hysteresis state machine ────────────────────────────────
    regime = _load_regime_state()
    final_color = _apply_hysteresis(regime, raw_color, veto_active)
    _save_regime_state(regime)

    composite_transparency["raw_truth_table_color"] = raw_color.value
    composite_transparency["hysteresis_applied"] = (final_color != raw_color)
    composite_transparency["regime_state"] = {
        "current": regime.current_regime.value,
        "pending_upgrade": regime.pending_upgrade.value if regime.pending_upgrade else None,
        "consecutive_days": regime.consecutive_days,
    }

    now = datetime.now()

    # Build summary
    parts = []
    for cat, sig in categories.items():
        parts.append(f"{cat.value}: {sig.composite_color.value}")
    if veto_active:
        parts.append("AI_HEALTH_VETO=ACTIVE")
    if final_color != raw_color:
        parts.append(f"HYSTERESIS: raw={raw_color.value}→applied={final_color.value}")
    summary = "; ".join(parts)

    result = CompositeSignal(
        categories=categories,
        overall_color=final_color,
        timestamp=now,
        summary=summary,
        veto_active=veto_active,
        composite_transparency=composite_transparency,
    )

    # Log signal state for history tracking
    _log_signal(result)

    return result


# ── Hysteresis state machine ─────────────────────────────────────────────


def _apply_hysteresis(
    state: RegimeState,
    raw_color: SignalColor,
    veto: bool,
) -> SignalColor:
    """Apply 3-day upgrade confirmation, instant downgrade.

    - Downgrades and veto: immediate, reset pending.
    - Upgrade: start or continue counting; only apply after 3 consecutive days.
    - Same color: reset pending.
    """
    today = date.today()
    current = state.current_regime

    # Veto always overrides immediately
    if veto:
        state.current_regime = SignalColor.RED
        state.pending_upgrade = None
        state.consecutive_days = 0
        state.last_updated = today
        return SignalColor.RED

    # Downgrade: immediate
    if color_is_worse(raw_color, current):
        logger.info("Regime downgrade: %s → %s (immediate)", current.value, raw_color.value)
        state.current_regime = raw_color
        state.pending_upgrade = None
        state.consecutive_days = 0
        state.last_updated = today
        return raw_color

    # Same as current: reset any pending upgrade
    if raw_color == current:
        state.pending_upgrade = None
        state.consecutive_days = 0
        state.last_updated = today
        return current

    # Upgrade: clamp target to one rank above current, needs confirmation.
    # Prevents multi-level jumps (e.g. RED→GREEN in 3 days) by forcing the
    # regime to walk the ladder: RED→ORANGE→YELLOW→GREEN, each step
    # requiring its own 3-day confirmation window.
    current_rank = _COLOR_RANK[current]
    raw_rank = _COLOR_RANK[raw_color]
    clamped_target = _RANK_TO_COLOR[min(raw_rank, current_rank + 1)]

    if state.pending_upgrade == clamped_target:
        # Continue counting (only increment if new day)
        if today > state.last_updated:
            state.consecutive_days += 1
        if state.consecutive_days >= _UPGRADE_CONFIRMATION_DAYS:
            logger.info(
                "Regime upgrade confirmed: %s → %s (after %d days; raw=%s)",
                current.value, clamped_target.value, state.consecutive_days,
                raw_color.value,
            )
            state.current_regime = clamped_target
            state.pending_upgrade = None
            state.consecutive_days = 0
            state.last_updated = today
            return clamped_target
    else:
        # New upgrade target — start counting
        state.pending_upgrade = clamped_target
        state.consecutive_days = 1

    state.last_updated = today
    return current  # Hold current regime until upgrade confirmed


# ── Regime state persistence ─────────────────────────────────────────────

_REGIME_FILE = "regime_state.json"


def _load_regime_state() -> RegimeState:
    """Load regime state from data/regime_state.json (or create default)."""
    path = get_data_dir() / _REGIME_FILE
    if not path.exists():
        return RegimeState()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return RegimeState.model_validate(data)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("Corrupt regime state file, resetting: %s", exc)
        return RegimeState()


def _save_regime_state(state: RegimeState) -> None:
    """Persist regime state to data/regime_state.json (atomic + locked)."""
    path = get_data_dir() / _REGIME_FILE
    try:
        from rewired.io import atomic_write, file_lock

        with file_lock(path):
            atomic_write(path, state.model_dump_json(indent=2))
    except OSError as exc:
        logger.error("Failed to save regime state: %s", exc)


# ── Signal history logging ───────────────────────────────────────────────


def _log_signal(signal: CompositeSignal) -> None:
    """Append signal to history if color changed."""
    data_dir = get_data_dir()
    history_path = data_dir / "signal_history.json"

    history = []
    if history_path.exists():
        try:
            with open(history_path, encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            history = []

    # Check if color changed
    last_color = history[-1]["to_color"] if history else None
    current_color = signal.overall_color.value

    if current_color != last_color:
        history.append({
            "timestamp": signal.timestamp.strftime("%Y-%m-%d %H:%M"),
            "from_color": last_color or "none",
            "to_color": current_color,
            "summary": signal.summary,
        })
        from rewired.io import atomic_write, file_lock

        with file_lock(history_path):
            atomic_write(history_path, json.dumps(history, indent=2))
