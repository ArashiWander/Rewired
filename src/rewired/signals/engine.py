"""Signal computation engine - orchestrates all signal calculators."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

from rewired import get_data_dir
from rewired.models.signals import CompositeSignal, SignalCategory
from rewired.signals.composite import compute_composite
from rewired.signals.macro_signal import calculate_macro_signal
from rewired.signals.sentiment_signal import calculate_sentiment_signal
from rewired.signals.ai_health_signal import calculate_ai_health_signal

console = Console()


def compute_signals() -> CompositeSignal:
    """Compute all signals and return the composite result."""
    console.print("[dim]Fetching macro data...[/dim]")
    macro = calculate_macro_signal()

    console.print("[dim]Fetching sentiment data...[/dim]")
    sentiment = calculate_sentiment_signal()

    console.print("[dim]Fetching AI health data...[/dim]")
    ai_health = calculate_ai_health_signal()

    categories = {
        SignalCategory.MACRO: macro,
        SignalCategory.SENTIMENT: sentiment,
        SignalCategory.AI_HEALTH: ai_health,
    }

    overall, veto_active, composite_transparency = compute_composite(categories)
    now = datetime.now()

    # Build summary
    parts = []
    for cat, sig in categories.items():
        parts.append(f"{cat.value}: {sig.composite_color.value}")
    if veto_active:
        parts.append("AI_HEALTH_VETO=ACTIVE")
    summary = "; ".join(parts)

    result = CompositeSignal(
        categories=categories,
        overall_color=overall,
        timestamp=now,
        summary=summary,
        veto_active=veto_active,
        composite_transparency=composite_transparency,
    )

    # Log signal state for history tracking
    _log_signal(result)

    return result


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
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
