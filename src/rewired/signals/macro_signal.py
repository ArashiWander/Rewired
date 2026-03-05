"""Macro signal calculator."""

from __future__ import annotations

from datetime import datetime

from rewired.data.macro import get_macro_readings
from rewired.models.signals import (
    CategorySignal,
    SignalCategory,
    SignalColor,
    SignalReading,
    SIGNAL_SCORES,
    score_to_color,
)


def calculate_macro_signal() -> CategorySignal:
    """Calculate composite macro signal from readings."""
    readings = get_macro_readings()
    now = datetime.now()

    if not readings:
        return CategorySignal(
            category=SignalCategory.MACRO,
            readings=[],
            composite_color=SignalColor.YELLOW,
            timestamp=now,
            explanation="No macro data available",
        )

    # Weighted average of signal scores
    total_weight = len(readings)
    weighted_score = sum(SIGNAL_SCORES[r.color] for r in readings) / total_weight
    composite = score_to_color(weighted_score)

    # Build explanation from worst readings
    worst = max(readings, key=lambda r: SIGNAL_SCORES[r.color])
    explanation = worst.detail

    return CategorySignal(
        category=SignalCategory.MACRO,
        readings=readings,
        composite_color=composite,
        timestamp=now,
        explanation=explanation,
    )
